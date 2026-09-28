from mcp.server.fastmcp import FastMCP
import sys
import os
import logging
from mcp.server.transport_security import TransportSecuritySettings
import os
import asyncio
from pymongo import MongoClient
import httpx
from bson import ObjectId
from datetime import datetime

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

mongodb_mcp = FastMCP(
    "mongodb_server",
    instructions="""
        MCP server for MongoDB and Kafka Connect sink management. Tools are grouped as: (1) health & status: mongo_check_status to verify MongoDB and Kafka Connect; (2) collection lifecycle: create_collection, list_collections, delete_collection; (3) Kafka Connect sink lifecycle: create_kafka_sink (verbatim), delete_kafka_sink, list_kafka_sinks; (4) direct data ops: insert_documents, query_documents. All MongoDB access uses the pymongo MongoClient cached via _get_client(). Kafka Connect interactions use the Connect REST API via httpx. Returns are JSON-serialisable dicts following the MCP return contract: top-level 'ok' reflects the actual combined success of all operations performed. Idempotency is explicit (created: False / deleted: False with reason when the resource already exists or is missing).
    """,
)

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongodb:27017")
KAFKA_CONNECT_URL = os.environ.get("KAFKA_CONNECT_URL", "http://kafka-connect:8083")
CONNECT_TIMEOUT = int(os.environ.get("CONNECT_TIMEOUT", "15"))
_CLIENT = None

def _make_client() -> MongoClient:
    return MongoClient(MONGO_URI)

def _get_client() -> MongoClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = _make_client()
    return _CLIENT

def _serialize_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    elif isinstance(value, datetime):
        return value.isoformat()
    elif isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_serialize_value(v) for v in value]
    else:
        return value

def _serialize_doc(doc):
    return {k: _serialize_value(v) for k, v in doc.items()}

def _connector_name_from_topic(topic: str) -> str:
    return f"mongo-sink-{topic.replace('.', '-') }"

@mongodb_mcp.tool()
async def mongo_check_status() -> dict:
    """
    Check that MongoDB and Kafka Connect are available. Returns ok=True only if both services responded successfully. Always reports the MongoDB database list when available and the Kafka Connect connector list when available. On partial failure, ok=False and errors are reported alongside any successful sub-results.
    """
    client = _get_client()
    try:
        dbs = await asyncio.to_thread(client.list_database_names)
    except Exception as e:
        return {"ok": False, "error": f"MongoDB error: {str(e)}"}

    # Check Kafka Connect
    try:
        async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT) as http:
            resp = await http.get(f"{KAFKA_CONNECT_URL}/connectors")
            resp.raise_for_status()
            connectors = resp.json()
    except Exception as e:
        # Mongo succeeded but Kafka failed -> overall failure per partial-failure rule
        return {"ok": False, "error": f"Kafka Connect error: {str(e)}", "databases": dbs}

    return {"ok": True, "databases": dbs, "connectors": connectors}

@mongodb_mcp.tool()
async def create_collection(database: str, collection: str) -> dict:
    """
    Create a collection in the given MongoDB database if it does not already exist. Returns created: True when created, created: False with reason when it already exists. On error returns ok=False and an error string.
    """
    client = _get_client()
    try:
        db = client[database]
        existing = await asyncio.to_thread(db.list_collection_names)
        if collection in existing:
            return {"ok": True, "created": False, "reason": "collection_already_exists"}
        await asyncio.to_thread(db.create_collection, collection)
        return {"ok": True, "created": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@mongodb_mcp.tool()
async def list_collections(database: str) -> dict:
    """
    List collections present in the specified MongoDB database. Returns ok=True and a 'collections' list on success. On error returns ok=False and an error string.
    """
    client = _get_client()
    try:
        db = client[database]
        collections = await asyncio.to_thread(db.list_collection_names)
        return {"ok": True, "collections": collections}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@mongodb_mcp.tool()
async def delete_collection(database: str, collection: str) -> dict:
    """
    Drop (delete) the named collection from the database, removing all documents. Idempotent: if the collection does not exist, returns ok=True with dropped: False and reason 'not_found'. On success returns dropped: True. On error returns ok=False and an error string.
    """
    client = _get_client()
    try:
        db = client[database]
        existing = await asyncio.to_thread(db.list_collection_names)
        if collection not in existing:
            return {"ok": True, "dropped": False, "reason": "not_found"}
        await asyncio.to_thread(db[collection].drop)
        return {"ok": True, "dropped": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@mongodb_mcp.tool()
async def delete_kafka_sink(topic: str) -> dict:
    """
    Delete a Kafka Connect MongoDB sink connector that was created for the given topic. Connector name is derived with the ConnectorNaming rule: 'mongo-sink-' + topic with dots replaced by hyphens. The MongoDB collection and its documents are preserved. Idempotent: if connector not found, returns ok=True with deleted: False and reason 'not_found'. On successful deletion returns deleted: True. On HTTP or other error returns ok=False with error details.
    """
    connector_name = _connector_name_from_topic(topic)
    try:
        async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT) as http:
            resp = await http.delete(f"{KAFKA_CONNECT_URL}/connectors/{connector_name}")
            if resp.status_code == 404:
                return {"ok": True, "deleted": False, "reason": "not_found", "connector": connector_name}
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                # Non-404 HTTP error
                return {"ok": False, "error": f"HTTP error {e.response.status_code}", "detail": e.response.text}
            return {"ok": True, "deleted": True, "connector": connector_name}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@mongodb_mcp.tool()
async def list_kafka_sinks() -> dict:
    """
    List Kafka Connect connectors whose names start with 'mongo-sink-'. For each such connector include its name and the status object retrieved from Connect's /connectors/{name}/status endpoint. Returns ok=True only if all relevant connector statuses were fetched successfully; partial failures cause ok=False and error details per-connector.
    """
    try:
        async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT) as http:
            list_resp = await http.get(f"{KAFKA_CONNECT_URL}/connectors")
            list_resp.raise_for_status()
            connector_names = list_resp.json()
    except Exception as e:
        return {"ok": False, "error": f"Failed to list connectors: {str(e)}"}

    results = []
    overall_ok = True
    for name in connector_names:
        if not name.startswith("mongo-sink-"):
            continue
        try:
            async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT) as http:
                status_resp = await http.get(f"{KAFKA_CONNECT_URL}/connectors/{name}/status")
                status_resp.raise_for_status()
                status = status_resp.json()
                results.append({"name": name, "status": status})
        except Exception as e:
            results.append({"name": name, "error": str(e)})
            overall_ok = False

    return {"ok": overall_ok, "connectors": results}

@mongodb_mcp.tool()
async def insert_documents(database: str, collection: str, documents: list) -> dict:
    """
    Insert one or more documents directly into the given MongoDB collection. 'documents' must be a non-empty list of dicts. Returns inserted_count on success and the inserted ids serialized as strings. On error returns ok=False and an error string.
    """
    if not documents or not isinstance(documents, list):
        return {"ok": False, "error": "`documents` must be a non-empty list"}
    client = _get_client()
    try:
        db = client[database]
        coll = db[collection]
        if len(documents) == 1:
            result = await asyncio.to_thread(coll.insert_one, documents[0])
            inserted_ids = [str(result.inserted_id)]
            inserted_count = 1
        else:
            result = await asyncio.to_thread(coll.insert_many, documents)
            inserted_ids = [str(_id) for _id in result.inserted_ids]
            inserted_count = len(inserted_ids)
        return {"ok": True, "inserted_count": inserted_count, "inserted_ids": inserted_ids}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@mongodb_mcp.tool()
async def query_documents(database: str, collection: str, filter_doc: dict | None = None, sort_field: str | None = None, sort_direction: int = 1, limit: int = 100) -> dict:
    """
    Query documents from a MongoDB collection. filter_doc is an optional Mongo filter dict. If no sort_field is provided and filter_doc is empty, results default to sorting descending on 'timestamp'. sort_direction is 1 (asc) or -1 (desc). limit bounds the number of returned documents. Returns serialized documents on success. On error returns ok=False and an error string.
    """
    client = _get_client()
    try:
        db = client[database]
        coll = db[collection]
        filter_doc = filter_doc or {}
        if not sort_field:
            # Default to most recent first on 'timestamp' when caller did not request sorting
            sort_field = "timestamp"
            sort_direction = -1
        cursor = coll.find(filter_doc).sort(sort_field, sort_direction).limit(limit)
        docs = await asyncio.to_thread(lambda: list(cursor))
        serialized_docs = [_serialize_doc(d) for d in docs]
        return {"ok": True, "documents": serialized_docs}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@mongodb_mcp.tool()
async def create_kafka_sink(topic: str, database: str, collection: str) -> dict:
    """
    Connect a Kafka topic to a MongoDB collection via Kafka Connect.
    Messages from the topic are continuously inserted as documents automatically.
    Always point sinks at processed topics, not raw ones.
    The collection must exist before calling this.

    topic:      Kafka topic to consume from  e.g. 'opcua.kuka.processed'
    database:   target MongoDB database      e.g. 'kuka'
    collection: target MongoDB collection    e.g. 'joint_readings'
    """
    connector_name = f"mongo-sink-{topic.replace('.', '-') }"
    config = {
        "name": connector_name,
        "config": {
            "connector.class": "com.mongodb.kafka.connect.MongoSinkConnector",
            "tasks.max": "1",
            "topics": topic,
            "connection.uri": MONGO_URI,
            "database": database,
            "collection": collection,
            "document.id.strategy": "com.mongodb.kafka.connect.sink.processor.id.strategy.UuidStrategy"
        }
    }
    try:
        async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT) as http:
            resp = await http.post(
                f"{KAFKA_CONNECT_URL}/connectors",
                json=config,
                headers={"Content-Type": "application/json"}
            )
            resp.raise_for_status()
            return {"ok": True, "status": "deployed", "connector": connector_name, "topic": topic, "database": database, "collection": collection}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            # Conflict means connector exists - report existing connector
            return {"ok": False, "status": "conflict_exists", "message": f"Connector {connector_name} already exists"}
        return {"ok": False, "status": "error", "error": str(e), "detail": e.response.text}


if __name__ == "__main__":
    mode = os.getenv("MCP_CONNECTION_MODE", "stdio").lower()
    logger.info(f"Starting MongoDB MCP server in {mode} mode")

    if mode == "http":
        PORT_VAR = "MONGODB_MCP_PORT"
        port = int(os.getenv("PORT") or os.getenv(PORT_VAR) or 8110)
        logger.info(f"HTTP mode - listening on port {port} (set PORT or {PORT_VAR} to override)")
        mongodb_mcp.settings.port = port
        mongodb_mcp.settings.host = "0.0.0.0"
        mongodb_mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        mongodb_mcp.run(transport="streamable-http")
    else:
        logger.info("STDIO mode")
        mongodb_mcp.run(transport="stdio")