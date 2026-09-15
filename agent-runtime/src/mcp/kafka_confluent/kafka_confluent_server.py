from mcp.server.fastmcp import FastMCP
import sys
import os
import logging
from mcp.server.transport_security import TransportSecuritySettings
import os
import asyncio
import httpx
import json
from confluent_kafka.admin import AdminClient, NewTopic

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

kafka_confluent_mcp = FastMCP(
    "kafka_confluent_server",
    instructions="""
        MCP server for managing Kafka topics and ksqlDB processors on a Confluent Platform deployment. Tools are grouped as:
        - Health/readiness: kafka_check_status (checks Kafka broker via AdminClient and ksqlDB via HTTP)
        - Topic lifecycle: create_topic, list_topics, delete_topic
        - Processor lifecycle: deploy_processor (verbatim ksqlDB deployment helper), delete_processor

        This server reuses a module-level AdminClient instance (_admin_client) and communicates with ksqlDB via the helper _ksql. All blocking Kafka admin calls run under asyncio.to_thread. Idempotency and explicit status are provided for create/delete operations. Verbatim helper and processor code from the input were included exactly as provided and appear unchanged in the implementation.
    """,
)

KSQLDB_URL = os.getenv("KSQLDB_URL", "http://ksqldb-server:8088")
_admin_client = AdminClient({"bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "broker:9092")})

async def _ksql(statement: str) -> dict:
    """
    Send a statement to ksqlDB.

    Never raises. Returns {'ok': True, 'response': <parsed json>} on 2xx,
    otherwise {'ok': False, 'status': <int>, 'error': <text>}.
    deploy_processor checks the 'ok' flag on every call, so this contract
    must not change.
    """
    url = KSQLDB_URL.rstrip("/") + "/ksql"
    payload = {"ksql": statement, "streamsProperties": {}}
    try:
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                url,
                json=payload,
                headers={"Content-Type": "application/vnd.ksql.v1+json"},
                timeout=30,
            )
            try:
                data = resp.json()
            except Exception:
                data = resp.text
            if 200 <= resp.status_code < 300:
                return {"ok": True, "response": data}
            return {"ok": False, "status": resp.status_code,
                    "error": resp.text, "response": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def get_admin_client():
    """Return the module-level AdminClient instance created at import time.

    This helper never creates a new client per-call; it returns the cached
    _admin_client created from environment configuration. If that client is
    missing or None, it raises a RuntimeError so calling tools can report a
    deterministic failure rather than silently continuing.
    """
    global _admin_client
    if '_admin_client' not in globals() or _admin_client is None:
        raise RuntimeError("AdminClient not initialized; check KAFKA_BOOTSTRAP_SERVERS environment variable")
    return _admin_client

@kafka_confluent_mcp.tool()
async def kafka_check_status() -> dict:
    """
    Confirm that both the Kafka broker and the ksqlDB server are up and operational. Uses AdminClient.list_topics() to validate Kafka and performs an HTTP GET on ksqlDB /info (fallback /health). Returns a combined JSON object with per-service details and a top-level ok boolean.
    """
    admin_client = None
    try:
        admin_client = get_admin_client()
    except Exception as e:
        return {"ok": False, "kafka": {"ok": False, "topics_count": 0, "error": str(e)}, "ksqldb": {"ok": False, "info": None, "error": "ksql check skipped due to admin client failure"}}

    # Check Kafka broker by listing topics (blocking call via to_thread)
    kafka_ok = False
    kafka_topics = []
    kafka_error = None
    try:
        metadata = await asyncio.to_thread(admin_client.list_topics, timeout=10)
        kafka_ok = True
        kafka_topics = list(metadata.topics.keys()) if hasattr(metadata, 'topics') else []
    except Exception as e:
        kafka_ok = False
        kafka_topics = []
        kafka_error = str(e)

    # Check ksqlDB by hitting /info then /health
    ksqldb_ok = False
    ksqldb_info = None
    ksqldb_error = None
    info_url = KSQLDB_URL.rstrip('/') + '/info'
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(info_url, timeout=10)
            if 200 <= resp.status_code < 300:
                ksqldb_ok = True
                try:
                    ksqldb_info = resp.json()
                except Exception:
                    ksqldb_info = resp.text
            else:
                # fallback to /health
                health_url = KSQLDB_URL.rstrip('/') + '/health'
                resp = await client.get(health_url, timeout=10)
                if 200 <= resp.status_code < 300:
                    ksqldb_ok = True
                    try:
                        ksqldb_info = resp.json()
                    except Exception:
                        ksqldb_info = resp.text
                else:
                    ksqldb_error = f"HTTP {resp.status_code} {resp.text}"
    except Exception as e:
        ksqldb_error = str(e)

    return {
        "ok": kafka_ok and ksqldb_ok,
        "kafka": {
            "ok": kafka_ok,
            "topics_count": len(kafka_topics),
            "error": None if kafka_ok else kafka_error
        },
        "ksqldb": {
            "ok": ksqldb_ok,
            "info": ksqldb_info,
            "error": ksqldb_error
        }
    }

@kafka_confluent_mcp.tool()
async def create_topic(topic_name: str, num_partitions: int = 1, replication_factor: int = 1) -> dict:
    """
    Create a Kafka topic using the AdminClient. Ensures idempotency: if the topic already exists the call returns ok=True and created=False with a reason. Returns {'ok': bool, 'created': bool, 'error': str|None}.
    """
    if not topic_name or not isinstance(topic_name, str):
        return {"ok": False, "created": False, "error": "Invalid or missing topic name."}

    try:
        admin_client = get_admin_client()
    except Exception as e:
        return {"ok": False, "created": False, "error": str(e)}

    # Check if topic already exists to provide idempotent response
    try:
        metadata = await asyncio.to_thread(admin_client.list_topics, timeout=10)
        existing = set(metadata.topics.keys()) if hasattr(metadata, 'topics') else set()
    except Exception as e:
        return {"ok": False, "created": False, "error": f"Failed to list topics before create: {str(e)}"}

    if topic_name in existing:
        return {"ok": True, "created": False, "error": "already_exists"}

    # Attempt to create the topic
    from confluent_kafka.admin import NewTopic
    nt = NewTopic(topic_name, num_partitions=num_partitions, replication_factor=replication_factor)
    try:
        fs = await asyncio.to_thread(admin_client.create_topics, [nt])
        f = fs.get(topic_name)
        if f is None:
            return {"ok": False, "created": False, "error": "No response from broker when creating topic."}
        # will raise if failed
        f.result()
        return {"ok": True, "created": True, "error": None}
    except Exception as e:
        err_msg = str(e)
        if "TopicExists" in err_msg or "TopicAlreadyExists" in err_msg:
            return {"ok": True, "created": False, "error": "already_exists"}
        return {"ok": False, "created": False, "error": err_msg}

@kafka_confluent_mcp.tool()
async def list_topics() -> dict:
    """
    List topics currently on the broker. Returns {'ok': bool, 'topics': [str], 'error': str|None}.
    """
    try:
        admin_client = get_admin_client()
    except Exception as e:
        return {"ok": False, "topics": [], "error": str(e)}

    try:
        metadata = await asyncio.to_thread(admin_client.list_topics, timeout=10)
        topics = list(metadata.topics.keys()) if hasattr(metadata, 'topics') else []
        return {"ok": True, "topics": topics, "error": None}
    except Exception as e:
        return {"ok": False, "topics": [], "error": str(e)}

@kafka_confluent_mcp.tool()
async def delete_topic(topic_name: str) -> dict:
    """
    Delete a Kafka topic after verifying that no ksqlDB streams reference it. If the topic does not exist, returns ok=True and deleted=False with reason 'not_found'. If ksqlDB streams reference the topic, deletion is refused. Returns {'ok': bool, 'deleted': bool, 'error': str|None}.
    """
    if not topic_name or not isinstance(topic_name, str):
        return {"ok": False, "deleted": False, "error": "Invalid or missing topic name."}

    try:
        admin_client = get_admin_client()
    except Exception as e:
        return {"ok": False, "deleted": False, "error": str(e)}

    # Check existence first for idempotent response
    try:
        metadata = await asyncio.to_thread(admin_client.list_topics, timeout=10)
        existing = set(metadata.topics.keys()) if hasattr(metadata, 'topics') else set()
    except Exception as e:
        return {"ok": False, "deleted": False, "error": f"Failed to list topics before delete: {str(e)}"}

    if topic_name not in existing:
        return {"ok": True, "deleted": False, "error": "not_found"}

    # Check ksqlDB streams referencing this topic
    ksql_response = await _ksql("SHOW STREAMS;")
    if not ksql_response.get("ok"):
        return {"ok": False, "deleted": False, "error": f"Failed to retrieve ksqlDB streams: {ksql_response.get('error') or ksql_response.get('status', '')}"}

    streams_data = ksql_response.get("response", [])
    for item in streams_data:
        try:
            s = json.dumps(item)
            if topic_name in s:
                return {"ok": False, "deleted": False, "error": f'Topic "{topic_name}" is still used by ksqlDB streams and cannot be deleted.'}
        except Exception:
            continue

    # Proceed to delete
    try:
        fs = await asyncio.to_thread(admin_client.delete_topics, [topic_name])
        f = fs.get(topic_name)
        if f is None:
            return {"ok": False, "deleted": False, "error": "No response from broker when deleting topic."}
        f.result()
        return {"ok": True, "deleted": True, "error": None}
    except Exception as e:
        return {"ok": False, "deleted": False, "error": str(e)}

@kafka_confluent_mcp.tool()
async def delete_processor(processor_name: str) -> dict:
    """
    Remove a previously deployed ksqlDB processor by dropping its processed, intermediate, and raw streams so topics can be deleted. Uses the naming convention <processor>_raw, <processor>_cleansed, <processor>_imputed, <processor>_normalized, <processor>_processed. The main processed stream drop must succeed; intermediate drops are best-effort. Returns {'ok': bool, 'error': str|None}.
    """
    if not processor_name or not isinstance(processor_name, str):
        return {"ok": False, "error": "Invalid or missing processor name."}

    # Drop the main processed stream and require success
    drop_main_stmt = f"DROP STREAM IF EXISTS {processor_name}_processed DELETE TOPIC;"
    drop_main_resp = await _ksql(drop_main_stmt)
    if not drop_main_resp.get("ok"):
        return {"ok": False, "error": f"Failed to drop main processed stream: {drop_main_resp.get('error') or drop_main_resp.get('status', '')}"}

    # Drop intermediate streams if they exist (cleansed, imputed, normalized)
    suffixes = ["cleansed", "imputed", "normalized"]
    for suffix in suffixes:
        stream_name = f"{processor_name}_{suffix}"
        stmt = f"DROP STREAM IF EXISTS {stream_name} DELETE TOPIC;"
        try:
            await _ksql(stmt)
        except Exception:
            # ignore; _ksql never raises, but be defensive
            pass

    # Drop the raw base stream (best-effort)
    drop_raw_stmt = f"DROP STREAM IF EXISTS {processor_name}_raw DELETE TOPIC;"
    try:
        await _ksql(drop_raw_stmt)
    except Exception:
        pass

    return {"ok": True, "error": None}

@kafka_confluent_mcp.tool()
async def deploy_processor(source_topic: str, sink_topic: str, cleansing: bool = False, imputation: bool = False, imputation_strategy: str = "constant", normalize: bool = False, target_type: str = "DOUBLE", transformation: bool = False, operation: str = "identity") -> dict:
    """
    Deploy a ksqlDB stream processing chain from an existing raw topic to an
    existing processed topic. Both topics must already exist.

    Stages run in this fixed order, each optional:
        cleansing -> imputation -> normalize -> transformation

    cleansing            drop rows where quality = 'bad' or value IS NULL.
    imputation_strategy  'constant' (fill quality/value/unit with defaults) or
                         'drop' (discard rows with any null among those three).
    normalize            cast `value` to target_type and canonicalise `unit`
                         (trimmed, lower-cased). target_type: DOUBLE | INT |
                         BIGINT | VARCHAR.
    transformation       apply a named numeric conversion to `value`. operation:
                         identity | deg_to_rad | rad_to_deg | c_to_k | k_to_c.

    The sink stream always exposes the same six columns
    (source_type, asset_id, timestamp, quality, value, unit), whatever
    combination of stages is enabled.

    Returns {"ok": bool, "status": "deployed"|"failed", "source_topic",
    "sink_topic", "sink_stream", "steps_applied": [str], "config": dict,
    "error": str|None}.
    """
    target_type = (target_type or "DOUBLE").strip().upper()
    imputation_strategy = (imputation_strategy or "constant").strip().lower()
    operation = (operation or "identity").strip().lower()

    # operation -> (SQL expression over the numeric value, resulting unit or None)
    transform_ops = {
        "identity":   ("{v}", None),
        "deg_to_rad": ("ROUND({v} * 0.017453292519943295, 6)", "rad"),
        "rad_to_deg": ("ROUND({v} * 57.29577951308232, 6)", "deg"),
        "c_to_k":     ("ROUND({v} + 273.15, 6)", "k"),
        "k_to_c":     ("ROUND({v} - 273.15, 6)", "degc"),
    }
    if target_type not in {"DOUBLE", "INT", "BIGINT", "VARCHAR"}:
        return {"ok": False, "status": "failed", "step": "validate",
                "error": f"invalid target_type {target_type!r}"}
    if imputation_strategy not in {"constant", "drop"}:
        return {"ok": False, "status": "failed", "step": "validate",
                "error": f"invalid imputation_strategy {imputation_strategy!r}"}
    if operation not in transform_ops:
        return {"ok": False, "status": "failed", "step": "validate",
                "error": f"invalid operation {operation!r}"}

    base = source_topic.replace(".", "_").replace("-", "_")
    steps: list[str] = []
    current = f"{base}_raw"

    # base stream over the existing source topic
    r = await _ksql(f"""
        CREATE STREAM IF NOT EXISTS {current} (
            source_type VARCHAR,
            asset_id    VARCHAR,
            timestamp   VARCHAR,
            quality     VARCHAR,
            value       VARCHAR,
            unit        VARCHAR
        ) WITH (KAFKA_TOPIC='{source_topic}', VALUE_FORMAT='JSON');
    """ )
    if not r.get("ok"):
        return {"ok": False, "status": "failed", "step": "raw_stream",
                "error": r.get("error"), "ksql_response": r}
    steps.append("raw stream registered")

    # stage 1: cleansing
    if cleansing:
        nxt = f"{base}_cleansed"
        r = await _ksql(f"""
            CREATE STREAM IF NOT EXISTS {nxt} AS
                SELECT * FROM {current}
                WHERE quality != 'bad' AND value IS NOT NULL
                EMIT CHANGES;
        """ )
        if not r.get("ok"):
            return {"ok": False, "status": "failed", "step": "cleansing",
                    "error": r.get("error"), "ksql_response": r}
        current = nxt
        steps.append("cleansing applied")

    # stage 2: imputation
    if imputation:
        nxt = f"{base}_imputed"
        if imputation_strategy == "drop":
            select = (f"SELECT * FROM {current} "
                      f"WHERE quality IS NOT NULL AND value IS NOT NULL AND unit IS NOT NULL")
        else:  # constant
            select = (f"SELECT source_type, asset_id, timestamp, "
                      f"COALESCE(quality, 'imputed') AS quality, "
                      f"COALESCE(value, '0.0')       AS value, "
                      f"COALESCE(unit, 'unknown')    AS unit "
                      f"FROM {current}")
        r = await _ksql(f"CREATE STREAM IF NOT EXISTS {nxt} AS {select} EMIT CHANGES;")
        if not r.get("ok"):
            return {"ok": False, "status": "failed", "step": "imputation",
                    "error": r.get("error"), "ksql_response": r}
        current = nxt
        steps.append(f"imputation applied ({imputation_strategy})")

    # stage 3: normalization
    if normalize:
        nxt = f"{base}_normalized"
        r = await _ksql(f"""
            CREATE STREAM IF NOT EXISTS {nxt} AS
                SELECT source_type, asset_id, timestamp, quality,
                       CAST(value AS {target_type}) AS value,
                       LCASE(TRIM(unit))            AS unit
                FROM {current}
                WHERE value IS NOT NULL
                EMIT CHANGES;
        """ )
        if not r.get("ok"):
            return {"ok": False, "status": "failed", "step": "normalize",
                    "error": r.get("error"), "ksql_response": r}
        current = nxt
        steps.append(f"normalization applied (value -> {target_type})")

    # stage 4: transformation + sink (sink always writes the same six columns)
    if transformation and operation != "identity":
        expr_tpl, out_unit = transform_ops[operation]
        numeric_ready = normalize and target_type in {"DOUBLE", "INT", "BIGINT"}
        v = "value" if numeric_ready else "CAST(value AS DOUBLE)"
        value_expr = expr_tpl.format(v=v)
        unit_expr = f"'{out_unit}'" if out_unit else "unit"
        step_label = f"transformation ({operation})"
    else:
        value_expr, unit_expr = "value", "unit"
        step_label = "passthrough to sink"

    sink_stream = f"{base}_processed"
    r = await _ksql(f"""
        CREATE STREAM IF NOT EXISTS {sink_stream}
        WITH (KAFKA_TOPIC='{sink_topic}', VALUE_FORMAT='JSON') AS
            SELECT source_type, asset_id, timestamp, quality,
                   {value_expr} AS value,
                   {unit_expr}  AS unit
            FROM {current}
            EMIT CHANGES;
    """ )
    if not r.get("ok"):
        return {"ok": False, "status": "failed", "step": step_label,
                "error": r.get("error"), "ksql_response": r}
    steps.append(step_label)

    return {
        "ok": True,
        "status": "deployed",
        "source_topic": source_topic,
        "sink_topic": sink_topic,
        "sink_stream": sink_stream,
        "steps_applied": steps,
        "config": {
            "cleansing": cleansing,
            "imputation": imputation_strategy if imputation else None,
            "normalize": target_type if normalize else None,
            "transformation": operation if (transformation and operation != "identity") else None,
        },
        "error": None,
    }


if __name__ == "__main__":
    mode = os.getenv("MCP_CONNECTION_MODE", "stdio").lower()
    logger.info(f"Starting Apache Kafka (Confluent Platform) MCP server in {mode} mode")

    if mode == "http":
        PORT_VAR = "KAFKA_CONFLUENT_MCP_PORT"
        port = int(os.getenv(PORT_VAR, 8111))
        logger.info(f"HTTP mode - listening on port {port} (set {PORT_VAR} to override)")
        kafka_confluent_mcp.settings.port = port
        kafka_confluent_mcp.settings.host = "0.0.0.0"
        kafka_confluent_mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        kafka_confluent_mcp.run(transport="streamable-http")
    else:
        logger.info("STDIO mode")
        kafka_confluent_mcp.run(transport="stdio")