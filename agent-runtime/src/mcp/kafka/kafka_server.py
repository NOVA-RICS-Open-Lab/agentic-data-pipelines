import os
import json
import httpx
from mcp.server.fastmcp import FastMCP
from confluent_kafka import KafkaException
from confluent_kafka.admin import AdminClient, NewTopic
from mcp.server.transport_security import TransportSecuritySettings

kafka_mcp = FastMCP("kafka-mcp")

BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "broker:9092")
KSQLDB_URL = os.environ.get("KSQLDB_URL", "http://ksqldb-server:8088")   ##METER NO CONFIG


# ── Internal helpers ──────────────────────────────────────────────────────────

def _make_admin() -> AdminClient:
    return AdminClient({"bootstrap.servers": BOOTSTRAP_SERVERS})


async def _ksql(statement: str) -> dict:
    """Send a SQL statement to ksqlDB and return the response."""
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{KSQLDB_URL}/ksql",
            json={"ksql": statement, "streamsProperties": {}},
            headers={"Content-Type": "application/vnd.ksql.v1+json"},
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()


# ── Tools ─────────────────────────────────────────────────────────────────────

@kafka_mcp.tool()
async def kafka_check_status() -> dict:
    """
    Check if both the Kafka broker and ksqlDB are reachable.
    Always call this first before setting up any pipeline.
    """
    broker_ok = False
    ksqldb_ok = False
    ksqldb_version = "unknown"
    broker_error = None
    ksqldb_error = None

    try:
        admin = _make_admin()
        admin.list_topics(timeout=5)
        broker_ok = True
    except Exception as e:
        broker_error = str(e)

    try:
        async with httpx.AsyncClient() as http:
            resp = await http.get(f"{KSQLDB_URL}/info", timeout=5)
            info = resp.json()
            ksqldb_ok = True
            ksqldb_version = info.get("KsqlServerInfo", {}).get("version", "unknown")
    except Exception as e:
        ksqldb_error = str(e)

    return {
        "broker": {
            "reachable": broker_ok,
            "address": BOOTSTRAP_SERVERS,
            "error": broker_error
        },
        "ksqldb": {
            "reachable": ksqldb_ok,
            "address": KSQLDB_URL,
            "version": ksqldb_version,
            "error": ksqldb_error
        }
    }


@kafka_mcp.tool()
async def create_topic(
    topic: str,
    num_partitions: int = 1,
    replication_factor: int = 1,
):
    """
    Create a Kafka topic. Always create the raw topic BEFORE deploying
    a Node-RED bridge or processor that references it.
    The processed topic is created automatically by ksqlDB when deploy_processor runs.

    Use naming convention:
      <protocol>.<asset>.raw       e.g. 'opcua.kuka.raw'
      <protocol>.<asset>.processed e.g. 'opcua.kuka.processed'

    topic:              topic name
    num_partitions:     number of partitions (default 1)
    replication_factor: keep at 1 for single-broker dev setup
    """
    admin = _make_admin()
    result = admin.create_topics([
        NewTopic(
            topic,
            num_partitions=num_partitions,
            replication_factor=replication_factor
        )
    ])
    for t, fut in result.items():
        try:
            fut.result()
            return {"status": "created", "topic": t}
        except KafkaException as e:
            return {"status": "error", "topic": t, "error": str(e)}


@kafka_mcp.tool()
async def delete_topic(topic: str):
    """
    Delete a Kafka topic and all its messages. This is irreversible.
    Always drop any active ksqlDB streams on this topic before deleting it,
    otherwise ksqlDB will error trying to read from a non-existent topic.

    topic: topic name to delete
    """
    # Check no ksqlDB streams are still pointing at this topic
    streams = await _ksql("SHOW STREAMS;")
    active = [
        s["name"] for s in streams[0].get("streams", [])
        if s.get("topic") == topic
    ]
    if active:
        return {
            "status": "error",
            "error": f"ksqlDB streams still reference this topic: {active}. Drop them first."
        }

    admin = _make_admin()
    result = admin.delete_topics([topic])
    for t, fut in result.items():
        try:
            fut.result()
            return {"status": "deleted", "topic": t}
        except KafkaException as e:
            return {"status": "error", "topic": t, "error": str(e)}


@kafka_mcp.tool()
async def list_topics() -> list:
    """
    List all user-created topics currently in the Kafka broker.
    Use this to verify a topic exists before deploying a bridge or processor.
    """
    admin = _make_admin()
    meta = admin.list_topics(timeout=5)
    return [
        {
            "topic": t,
            "partitions": len(meta.topics[t].partitions)
        }
        for t in sorted(meta.topics)
        if not t.startswith("__")           # filter Kafka internal topics
        and not t.startswith("agentic_ksql") # filter ksqlDB internal topics
    ]



@kafka_mcp.tool()
async def deploy_processor(
    source_topic: str,
    sink_topic: str,
    source_schema: dict = {},
    cleansing: bool = False,
    normalize: bool = False,
    transformation: bool = False,
    imputation: bool = False,
) -> dict:
    """
    Deploy a ksqlDB stream processor between two Kafka topics.
    ksqlDB runs the processing continuously and natively inside the Kafka ecosystem.
    Processing order is always: cleansing → imputation → normalize → transformation.
    source_topic must exist before calling this.
    sink_topic must also exist before calling this — always create it explicitly first.

    source_topic:   raw input topic    e.g. 'opcua.kuka.raw'
    sink_topic:     processed output   e.g. 'opcua.kuka.processed'
    source_schema:  ALWAYS pass an empty dict {}. The processor already hardcodes all
                    required fields (source_type, asset_id, timestamp, quality, value, unit).
    cleansing:      filter nulls and bad quality messages
    normalize:      enforce consistent field names and types
    transformation: apply unit conversions and derived calculations
    imputation:     fill missing values with safe defaults
    """

    # Sanitize topic name to valid ksqlDB stream name
    # e.g. 'opcua.kuka.raw' → 'opcua_kuka_raw'
    stream_base = source_topic.replace(".", "_").replace("-", "_")
    results = []
    current_stream = f"{stream_base}_raw"

    # ── Step 1: Register the raw stream ───────────────────────────────────────
    # Build schema fields from the source_schema dict the agent passes in
    schema_fields = ",\n            ".join(
        f"{field} {dtype}"
        for field, dtype in source_schema.items()
    )
    await _ksql(f"""
        CREATE STREAM IF NOT EXISTS {current_stream} (
            source_type VARCHAR,
            asset_id    VARCHAR,
            timestamp   VARCHAR,
            quality     VARCHAR,
            value       VARCHAR,
            unit        VARCHAR
        ) WITH (
            KAFKA_TOPIC='{source_topic}',
            VALUE_FORMAT='JSON'
        );
    """)
    results.append("raw stream registered")

    # ── Step 2: Cleansing ─────────────────────────────────────────────────────
    if cleansing:
        next_stream = f"{stream_base}_cleansed"
        null_checks = " AND ".join(
            f"{field} IS NOT NULL" for field in source_schema.keys()
        )
        where_clause = "WHERE quality != 'bad'"
        if null_checks:
            where_clause += f" AND {null_checks}"
        
        await _ksql(f"""
            CREATE STREAM IF NOT EXISTS {next_stream} AS
                SELECT *
                FROM {current_stream}
                {where_clause}
                EMIT CHANGES;
            """)
        current_stream = next_stream 
        results.append("cleansing applied")

    # ── Step 3: Imputation ────────────────────────────────────────────────────
    if imputation:
        next_stream = f"{stream_base}_imputed"
        await _ksql(f"""
            CREATE STREAM IF NOT EXISTS {next_stream} AS
                SELECT
                    source_type,
                    asset_id,
                    timestamp,
                    COALESCE(quality, 'imputed') AS quality,
                    COALESCE(value, 0.0)         AS value,
                    COALESCE(unit, 'unknown')    AS unit
                FROM {current_stream}
                EMIT CHANGES;
        """)
        current_stream = next_stream
        results.append("imputation applied")

    # ── Step 4: Normalization ─────────────────────────────────────────────────
    if normalize:
        next_stream = f"{stream_base}_normalized"
        await _ksql(f"""
            CREATE STREAM IF NOT EXISTS {next_stream} AS
                SELECT
                    COALESCE(source_type, 'unknown') AS source_type,
                    COALESCE(asset_id, 'unknown')    AS asset_id,
                    timestamp,
                    quality,
                    value,
                    unit
                FROM {current_stream}
                EMIT CHANGES;
        """)
        current_stream = next_stream
        results.append("normalization applied")

    # ── Step 5: Transformation ────────────────────────────────────────────────
    # This is always the final step so it writes directly to sink_topic
    if transformation:
        next_stream = f"{stream_base}_processed"
        await _ksql(f"""
            CREATE STREAM IF NOT EXISTS {next_stream}
            WITH (KAFKA_TOPIC='{sink_topic}', VALUE_FORMAT='JSON') AS
                SELECT
                    source_type,
                    asset_id,
                    timestamp,
                    quality,
                    value                           AS value_deg,
                    ROUND(value * 0.0174533, 6)     AS value_rad,
                    unit
                FROM {current_stream}
                EMIT CHANGES;
        """)
        results.append("transformation applied")

    else:
        # No transformation — point whatever the last step was at sink_topic
        next_stream = f"{stream_base}_processed"
        await _ksql(f"""
            CREATE STREAM IF NOT EXISTS {next_stream}
            WITH (KAFKA_TOPIC='{sink_topic}', VALUE_FORMAT='JSON') AS
                SELECT * FROM {current_stream}
                EMIT CHANGES;
        """)
        results.append("output stream created")

    return {
        "status": "deployed",
        "source_topic": source_topic,
        "sink_topic": sink_topic,
        "steps_applied": results
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8084))
    kafka_mcp.settings.port = port
    kafka_mcp.settings.host = "0.0.0.0"
    kafka_mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    kafka_mcp.run(transport="streamable-http")