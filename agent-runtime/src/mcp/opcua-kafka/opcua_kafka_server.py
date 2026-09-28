import asyncio
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP("opcua-kafka-bridge")

COMPOSE_FILE = os.getenv("COMPOSE_FILE", "/workspace/docker-compose.yml")
PROJECT_NAME = os.getenv("COMPOSE_PROJECT_NAME", "agentic-data-pipelines")
SERVICE = "opcua-kafka"
TOPIC = "opcua.kuka.raw"


async def _compose(*args: str, timeout: float = 120) -> dict:
    """Run one docker compose command. Never raises."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "compose", "-f", COMPOSE_FILE, "-p", PROJECT_NAME, *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"ok": False, "error": f"docker compose {' '.join(args)} timed out"}
    if proc.returncode != 0:
        return {"ok": False, "error": err.decode(errors="replace").strip()}
    return {"ok": True, "error": None, "stdout": out.decode(errors="replace").strip()}


async def _running() -> dict:
    r = await _compose("ps", "--status", "running", "-q", SERVICE)
    if not r["ok"]:
        return r
    return {"ok": True, "error": None, "running": bool(r["stdout"])}


async def _reachable(host: str, port: int, timeout: float = 5.0) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except Exception:
        return False
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass
    return True


@mcp.tool()
async def bridge_check_status() -> dict:
    """Check Docker Compose, the OPC UA server and the Kafka broker before starting the bridge."""
    docker = await _running()
    opcua = await _reachable("kuka-robot", 4849)
    kafka = await _reachable("broker", 9092)
    ok = docker["ok"] and opcua and kafka
    return {
        "ok": ok,
        "error": None if ok else "one or more checks failed",
        "docker_compose": docker["ok"],
        "docker_error": docker.get("error"),
        "opcua_reachable": opcua,
        "kafka_reachable": kafka,
        "bridge_running": docker.get("running"),
    }


@mcp.tool()
async def start_bridge() -> dict:
    """Start the OPC UA to Kafka bridge (writes to opcua.kuka.raw). The topic must exist first."""
    state = await _running()
    if not state["ok"]:
        return {"ok": False, "error": state["error"]}
    if state["running"]:
        return {"ok": True, "error": None, "already_running": True, "topic": TOPIC}

    r = await _compose("up", "-d", "--no-deps", SERVICE)
    if not r["ok"]:
        return {"ok": False, "error": r["error"]}

    for _ in range(15):  # up to ~30 s
        await asyncio.sleep(2)
        s = await _running()
        if s["ok"] and s["running"]:
            await asyncio.sleep(5)  # must still be running, not crash-looping
            s = await _running()
            if s["ok"] and s["running"]:
                return {"ok": True, "error": None, "already_running": False, "topic": TOPIC}
            break

    logs = await _compose("logs", "--tail", "20", SERVICE)
    return {"ok": False, "error": "bridge did not stay running",
            "logs": logs.get("stdout") if logs["ok"] else logs["error"]}


@mcp.tool()
async def stop_bridge() -> dict:
    """Stop the bridge. The container, topic and data are kept."""
    state = await _running()
    if not state["ok"]:
        return {"ok": False, "error": state["error"]}
    if not state["running"]:
        return {"ok": True, "error": None, "already_stopped": True}

    r = await _compose("stop", SERVICE)
    if not r["ok"]:
        return {"ok": False, "error": r["error"]}

    s = await _running()
    if not s["ok"]:
        return {"ok": False, "error": s["error"]}
    if s["running"]:
        return {"ok": False, "error": "bridge is still running after stop"}
    return {"ok": True, "error": None, "already_stopped": False}


@mcp.tool()
async def bridge_status() -> dict:
    """Report whether the bridge is running, its status line and its last 20 log lines."""
    s = await _running()
    if not s["ok"]:
        return {"ok": False, "error": s["error"]}
    ps = await _compose("ps", "-a", SERVICE)
    logs = await _compose("logs", "--tail", "20", SERVICE)
    return {
        "ok": True,
        "error": None,
        "running": s["running"],
        "topic": TOPIC,
        "ps": ps["stdout"] if ps["ok"] else ps["error"],
        "logs": logs["stdout"] if logs["ok"] else logs["error"],
    }


if __name__ == "__main__":
    mcp.settings.port = int(os.getenv("PORT", 8097))
    mcp.settings.host = "0.0.0.0"
    mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    mcp.run(transport="streamable-http")