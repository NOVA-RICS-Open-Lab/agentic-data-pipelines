import json
import logging
import os
import subprocess
import yaml
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from src.mcp.docker import deployer

logger = logging.getLogger(__name__)

docker_mcp = FastMCP("docker-mcp")

COMPOSE_FILE = os.getenv("COMPOSE_FILE", "/app/docker-compose.yml")
PROJECT_NAME = os.getenv("COMPOSE_PROJECT_NAME", "agentic-data-pipelines")


@docker_mcp.custom_route("/deploy/suggest-port", methods=["GET"])
async def suggest_port(request: Request) -> JSONResponse:
    return JSONResponse({"port": deployer.suggest_port()})


@docker_mcp.custom_route("/deploy", methods=["POST"])
async def deploy_server(request: Request) -> StreamingResponse:
    """Promote a generated MCP server into a running docker-compose service.

    Body: {"file_path": str, "port": int}. Streams NDJSON log lines back;
    the console proxies this straight through to the operator's browser.
    """
    body = await request.json()
    file_path = body.get("file_path")
    port = body.get("port")

    async def event_stream():
        if not file_path or not isinstance(port, int):
            yield json.dumps({"type": "error", "message": "file_path and port are required"}) + "\n"
            return
        try:
            async for line in deployer.deploy(file_path, port):
                yield json.dumps({"type": "log", "line": line}) + "\n"
            yield json.dumps({"type": "done", "success": True}) + "\n"
        except deployer.DeployError as e:
            logger.warning(f"Deploy rejected: {e}")
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"
        except Exception as e:
            logger.exception("Unexpected deploy failure")
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8087))
    docker_mcp.settings.port = port
    docker_mcp.settings.host = "0.0.0.0"
    docker_mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    docker_mcp.run(transport="streamable-http")
