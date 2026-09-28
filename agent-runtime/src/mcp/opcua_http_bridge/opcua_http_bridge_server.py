from mcp.server.fastmcp import FastMCP
import sys
import os
import logging
from mcp.server.transport_security import TransportSecuritySettings
import os
import re
import socket
import requests
import subprocess
import asyncio
import time

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

opcua_http_bridge_mcp = FastMCP(
    "opcua_http_bridge_server",
    instructions="""
        MCP server for the OpcuaHttpBridge Docker Compose based bridge. Tools grouped by purpose:
        - Status tools: StatusCheck (checks docker-compose availability, TCP connectivity to the OPC UA host:port, HTTP health of the receiver, service run state for opcua-ingest and opcua-http, and fetches last 20 lines of opcua-http logs).
        - Lifecycle tools: StartBridge (starts opcua-ingest and opcua-http via docker compose with MongoDB database/collection environment variables) and StopBridge (stops the services in correct order without removing containers).
        All connection configuration is read from environment variables. Tools are async and use asyncio.to_thread for blocking subprocess calls. The server exposes exactly the tools named in the capability specification.
    """,
)

COMPOSE_FILE = os.getenv("COMPOSE_FILE", "/workspace/docker-compose.yml")
PROJECT_NAME = os.getenv("COMPOSE_PROJECT_NAME", "agentic-data-pipelines")
BRIDGE_SERVICE = "opcua-http"
RECEIVER_SERVICE = "opcua-ingest"
OPCUA_HOST, OPCUA_PORT = "kuka-robot", 4849
RECEIVER_HEALTH_URL = "http://opcua-ingest:8098/health"
NAME_PATTERN = r"^[A-Za-z0-9_-]{1,63}$"

def _run_subprocess_sync(cmd, env=None):
    """Run subprocess.run in a synchronous helper. Returns (returncode, stdout, stderr) strings."""
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except Exception as e:
        return 1, "", str(e)


def docker_compose_cmd(args, env=None):
    """Run docker compose commands using COMPOSE_FILE and PROJECT_NAME. Returns (retcode, stdout, stderr)."""
    cmd = ["docker", "compose", "-f", COMPOSE_FILE, "-p", PROJECT_NAME] + args
    return _run_subprocess_sync(cmd, env=env)


def validate_name(name: str) -> bool:
    """Validate database/collection name against NAME_PATTERN."""
    return re.match(NAME_PATTERN, name) is not None


def check_tcp_connect(host: str, port: int, timeout: int = 5) -> bool:
    """Try to open a TCP connection to host:port with timeout seconds."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((host, port))
        return True
    except Exception:
        return False


def check_http_health(url: str, timeout: int = 3) -> bool:
    """Perform an HTTP GET against url and return True if status_code == 200."""
    try:
        r = requests.get(url, timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        return False


def get_running_services():
    """Return a list of service names that docker compose reports as running, or None on error."""
    retcode, stdout, stderr = docker_compose_cmd(["ps", "--services", "--filter", "status=running"])
    if retcode != 0:
        return None
    services = [line.strip() for line in stdout.splitlines() if line.strip()]
    return services


def get_logs_tail(service: str, lines: int = 20):
    """Return the last `lines` of logs for `service` as a string, or (None, stderr) on error."""
    retcode, stdout, stderr = docker_compose_cmd(["logs", "--tail", str(lines), service])
    if retcode != 0:
        return None, stderr
    return stdout, None


@opcua_http_bridge_mcp.tool()
async def StatusCheck() -> dict:
    """
    Check overall system status. Verifies: docker compose availability, TCP connectivity to OPC UA server (OPCUA_HOST:OPCUA_PORT) with 5s timeout, HTTP GET of RECEIVER_HEALTH_URL returns 200, whether opcua-ingest and opcua-http are running, and returns the last 20 lines of opcua-http logs. The returned dict contains keys: compose_available (bool), opcua_tcp_connect (bool), receiver_health (bool), receiver_running (bool), bridge_running (bool), bridge_logs_tail (str), ok (bool). 'ok' is true only when all checks required by the capability pass.
    """
    # Check docker compose availability
    retcode, _, _ = await asyncio.to_thread(docker_compose_cmd, ["ps"])  # returns (retcode, stdout, stderr)
    compose_available = (retcode == 0)

    # Check OPC UA TCP connectivity
    opcua_tcp_connect = await asyncio.to_thread(check_tcp_connect, OPCUA_HOST, OPCUA_PORT, 5)

    # Check receiver HTTP health endpoint
    receiver_health = await asyncio.to_thread(check_http_health, RECEIVER_HEALTH_URL, 3)

    # Check running services
    running_services = await asyncio.to_thread(get_running_services)
    if running_services is None:
        running_services = []
    receiver_running = RECEIVER_SERVICE in running_services
    bridge_running = BRIDGE_SERVICE in running_services

    # Get last 20 lines of bridge logs
    logs, log_err = await asyncio.to_thread(get_logs_tail, BRIDGE_SERVICE, 20)
    bridge_logs_tail = logs if logs is not None else f"(error fetching logs: {log_err})"

    ok = all([compose_available, opcua_tcp_connect, receiver_health, receiver_running, bridge_running])

    return {
        "compose_available": compose_available,
        "opcua_tcp_connect": opcua_tcp_connect,
        "receiver_health": receiver_health,
        "receiver_running": receiver_running,
        "bridge_running": bridge_running,
        "bridge_logs_tail": bridge_logs_tail,
        "ok": ok
    }


@opcua_http_bridge_mcp.tool()
async def StartBridge(mongodb_database: str, mongodb_collection: str) -> dict:
    """
    Start the opcua-ingest and opcua-http services via docker compose. Validates mongodb_database and mongodb_collection against NAME_PATTERN. Sets environment variables MONGODB_DATABASE and MONGODB_COLLECTION for the docker compose invocation. Returns dict with ok (bool). On success also returns started: True and changed: True. If services were already running, returns started: False and changed: False and ok: True.
    """
    # Validate names
    if not validate_name(mongodb_database) or not validate_name(mongodb_collection):
        return {"ok": False, "reason": "invalid database or collection name"}

    # Check if both services already running
    running_services = await asyncio.to_thread(get_running_services)
    if running_services is None:
        running_services = []

    if RECEIVER_SERVICE in running_services and BRIDGE_SERVICE in running_services:
        return {"ok": True, "started": False, "reason": "already_running", "changed": False}

    # Prepare environment for docker compose
    env = os.environ.copy()
    env["MONGODB_DATABASE"] = mongodb_database
    env["MONGODB_COLLECTION"] = mongodb_collection

    # Run docker compose up -d for both services
    cmd = ["docker", "compose", "-f", COMPOSE_FILE, "-p", PROJECT_NAME, "up", "-d", RECEIVER_SERVICE, BRIDGE_SERVICE]
    retcode, stdout, stderr = await asyncio.to_thread(_run_subprocess_sync, cmd, env)
    if retcode != 0:
        return {"ok": False, "reason": f"docker compose up failed: {stderr.strip()}"}

    # Allow some time for services to come up
    await asyncio.sleep(5)

    # Verify bridge is running
    running_services = await asyncio.to_thread(get_running_services)
    if running_services is None:
        running_services = []

    if BRIDGE_SERVICE in running_services:
        return {"ok": True, "started": True, "changed": True}
    else:
        return {"ok": False, "reason": "Bridge service not running after start"}


@opcua_http_bridge_mcp.tool()
async def StopBridge() -> dict:
    """
    Stop opcua-http first, then opcua-ingest using docker compose stop. Verifies both services are stopped. Does not remove containers or data. Returns ok: True on success; otherwise ok: False with a reason.
    """
    # Stop the bridge service first
    cmd_bridge = ["docker", "compose", "-f", COMPOSE_FILE, "-p", PROJECT_NAME, "stop", BRIDGE_SERVICE]
    retcode, stdout, stderr = await asyncio.to_thread(_run_subprocess_sync, cmd_bridge)
    if retcode != 0:
        return {"ok": False, "reason": f"Failed to stop bridge service: {stderr.strip()}"}

    # Then stop the receiver service
    cmd_receiver = ["docker", "compose", "-f", COMPOSE_FILE, "-p", PROJECT_NAME, "stop", RECEIVER_SERVICE]
    retcode, stdout, stderr = await asyncio.to_thread(_run_subprocess_sync, cmd_receiver)
    if retcode != 0:
        return {"ok": False, "reason": f"Failed to stop receiver service: {stderr.strip()}"}

    # Verify both services are stopped
    running_services = await asyncio.to_thread(get_running_services)
    if running_services is None:
        running_services = []

    if BRIDGE_SERVICE not in running_services and RECEIVER_SERVICE not in running_services:
        return {"ok": True}
    else:
        return {"ok": False, "reason": "One or both services still running after stop"}



if __name__ == "__main__":
    mode = os.getenv("MCP_CONNECTION_MODE", "stdio").lower()
    logger.info(f"Starting OpcuaHttpBridge MCP server in {mode} mode")

    if mode == "http":
        PORT_VAR = "OPCUA_HTTP_BRIDGE_MCP_PORT"
        port = int(os.getenv("PORT") or os.getenv(PORT_VAR) or 8123)
        logger.info(f"HTTP mode - listening on port {port} (set PORT or {PORT_VAR} to override)")
        opcua_http_bridge_mcp.settings.port = port
        opcua_http_bridge_mcp.settings.host = "0.0.0.0"
        opcua_http_bridge_mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        opcua_http_bridge_mcp.run(transport="streamable-http")
    else:
        logger.info("STDIO mode")
        opcua_http_bridge_mcp.run(transport="stdio")