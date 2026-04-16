import os
import httpx
from mcp.server.fastmcp import FastMCP
from pymongo import MongoClient, DESCENDING
from pymongo.errors import PyMongoError
from mcp.server.transport_security import TransportSecuritySettings

mongo_mcp = FastMCP("mongo-mcp")

MONGO_URI         = os.environ.get("MONGO_URI", "mongodb://admin:password123@mongodb:27017")
KAFKA_CONNECT_URL = os.environ.get("KAFKA_CONNECT_URL", "http://kafka-connect:8083")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _make_client() -> MongoClient:
    return MongoClient(MONGO_URI)


# ── Health ────────────────────────────────────────────────────────────────────

@mongo_mcp.tool()
async def mongo_check_status() -> dict:
    """
    Check if MongoDB and Kafka Connect are reachable.
    Always call this first before setting up any sink or querying data.
    """
    mongo_ok = False
    connect_ok = False
    mongo_error = None
    connect_error = None
    databases = []

    try:
        client = _make_client()
        client.admin.command("ping")
        databases = [
            d for d in client.list_database_names()
            if d not in ["admin", "config", "local"]
        ]
        mongo_ok = True
    except Exception as e:
        mongo_error = str(e)

    try:
        async with httpx.AsyncClient() as http:
            resp = await http.get(f"{KAFKA_CONNECT_URL}/connectors", timeout=5)
            resp.raise_for_status()
            connect_ok = True
    except Exception as e:
        connect_error = str(e)

    return {
        "mongodb": {
            "reachable": mongo_ok,
            "address": MONGO_URI,
            "databases": databases,
            "error": mongo_error
        },
        "kafka_connect": {
            "reachable": connect_ok,
            "address": KAFKA_CONNECT_URL,
            "error": connect_error
        }
    }


# ── Collection Management ─────────────────────────────────────────────────────

@mongo_mcp.tool()
async def create_collection(
    database: str,
    collection: str,
) -> dict:
    """
    Create a MongoDB collection.
    Always create the collection BEFORE deploying a Kafka sink that writes to it.

    Use naming convention matching your Kafka topics:
      database:   asset or project name  e.g. 'kuka'
      collection: data type              e.g. 'joint_readings'

    database:   database name
    collection: collection name
    """
    try:
        client = _make_client()
        client[database].create_collection(collection)
        return {
            "status": "created",
            "database": database,
            "collection": collection
        }
    except PyMongoError as e:
        return {"status": "error", "error": str(e)}


@mongo_mcp.tool()
async def list_collections(database: str) -> list:
    """
    List all collections in a database.
    Use this to verify a collection exists before deploying a sink against it.

    database: database name to list collections from
    """
    try:
        client = _make_client()
        return client[database].list_collection_names()
    except PyMongoError as e:
        return [{"error": str(e)}]


@mongo_mcp.tool()
async def delete_collection(
    database: str,
    collection: str,
) -> dict:
    """
    Delete a MongoDB collection and all its documents. This is irreversible.
    Always stop any active Kafka sink writing to this collection before deleting.

    database:   database name
    collection: collection name to delete
    """
    try:
        client = _make_client()
        client[database].drop_collection(collection)
        return {
            "status": "deleted",
            "database": database,
            "collection": collection
        }
    except PyMongoError as e:
        return {"status": "error", "error": str(e)}


# ── Kafka Connect Sink ────────────────────────────────────────────────────────

@mongo_mcp.tool()
async def create_kafka_sink(
    topic: str,
    database: str,
    collection: str,
) -> dict:
    """
    Connect a Kafka topic to a MongoDB collection via Kafka Connect.
    Messages from the topic are continuously inserted as documents automatically.
    Always point sinks at processed topics, not raw ones.
    The collection must exist before calling this — call create_collection first.

    topic:      Kafka topic to consume from  e.g. 'opcua.kuka.processed'
    database:   target MongoDB database      e.g. 'kuka'
    collection: target MongoDB collection    e.g. 'joint_readings'
    """
    connector_name = f"mongo-sink-{topic.replace('.', '-')}"
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
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"{KAFKA_CONNECT_URL}/connectors",
                json=config,
                headers={"Content-Type": "application/json"},
                timeout=15
            )
            resp.raise_for_status()
            return {
                "status": "deployed",
                "connector": connector_name,
                "topic": topic,
                "database": database,
                "collection": collection
            }
    except httpx.HTTPStatusError as e:
        return {"status": "error", "error": str(e), "detail": e.response.text}


@mongo_mcp.tool()
async def delete_kafka_sink(topic: str) -> dict:
    """
    Stop and remove a Kafka Connect sink connector.
    The collection and its data are preserved — only the connector is removed.

    topic: Kafka topic the sink is consuming from e.g. 'opcua.kuka.processed'
    """
    connector_name = f"mongo-sink-{topic.replace('.', '-')}"
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.delete(
                f"{KAFKA_CONNECT_URL}/connectors/{connector_name}",
                timeout=15
            )
            if resp.status_code == 404:
                return {"status": "not_found", "connector": connector_name}
            resp.raise_for_status()
            return {"status": "deleted", "connector": connector_name}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "error": str(e)}


@mongo_mcp.tool()
async def list_kafka_sinks() -> list:
    """
    List all active Kafka Connect sink connectors and their status.
    Use this to verify a sink is running after deployment.
    Status will be one of: RUNNING, PAUSED, FAILED.
    """
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{KAFKA_CONNECT_URL}/connectors?expand=status",
                timeout=10
            )
            resp.raise_for_status()
            connectors = resp.json()

        return [
            {
                "connector": name,
                "status": info["status"]["connector"]["state"],
                "tasks": [
                    {
                        "id": t["id"],
                        "state": t["state"]
                    }
                    for t in info["status"].get("tasks", [])
                ]
            }
            for name, info in connectors.items()
            if "mongo-sink" in name
        ]
    except httpx.HTTPStatusError as e:
        return [{"error": str(e)}]


# ── Direct Insert (non-Kafka sources) ─────────────────────────────────────────

@mongo_mcp.tool()
async def insert_document(
    database: str,
    collection: str,
    document: dict,
) -> dict:
    """
    Insert a single document directly into MongoDB.
    Use this for sources that write directly to MongoDB
    rather than going through a Kafka topic.

    database:   target database
    collection: target collection
    document:   JSON document to insert
    """
    try:
        client = _make_client()
        result = client[database][collection].insert_one(document)
        return {
            "status": "inserted",
            "database": database,
            "collection": collection,
            "inserted_id": str(result.inserted_id)
        }
    except PyMongoError as e:
        return {"status": "error", "error": str(e)}


# ── Context queries (agent reads) ─────────────────────────────────────────────

@mongo_mcp.tool()
async def get_latest(
    database: str,
    collection: str,
    n: int = 10,
) -> list:
    """
    Get the n most recent documents from a collection.
    Use this to give the agent context about the current state of an asset
    before making decisions e.g. check last Kuka readings before adjusting pipeline.

    database:   database name
    collection: collection name
    n:          number of documents to return (default 10)
    """
    try:
        client = _make_client()
        docs = list(
            client[database][collection]
            .find({}, {"_id": 0})
            .sort("timestamp", DESCENDING)
            .limit(n)
        )
        return docs
    except PyMongoError as e:
        return [{"error": str(e)}]


@mongo_mcp.tool()
async def query_documents(
    database: str,
    collection: str,
    filter: dict = {},
    limit: int = 100,
) -> list:
    """
    Query documents from a MongoDB collection using a MongoDB filter.
    Use this when the agent needs specific historical data for context.

    Examples:
      filter={"quality": "good"}
      filter={"data.value_deg": {"$gt": 90}}
      filter={"source_type": "opcua", "asset_id": "kuka"}

    database:   database name
    collection: collection name
    filter:     MongoDB query filter (default {} returns all documents)
    limit:      maximum documents to return (default 100)
    """
    try:
        client = _make_client()
        docs = list(
            client[database][collection]
            .find(filter, {"_id": 0})
            .limit(limit)
        )
        return docs
    except PyMongoError as e:
        return [{"error": str(e)}]


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8085))
    mongo_mcp.settings.port = port
    mongo_mcp.settings.host = "0.0.0.0"
    mongo_mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    mongo_mcp.run(transport="streamable-http")