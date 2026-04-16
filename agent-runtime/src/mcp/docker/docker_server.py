import os
import subprocess
import yaml
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

docker_mcp = FastMCP("docker-mcp")

COMPOSE_FILE = os.getenv("COMPOSE_FILE", "/app/docker-compose.yml")
PROJECT_NAME = os.getenv("COMPOSE_PROJECT_NAME", "agentic-data-pipelines")

@docker_mcp.tool()
async def start_opcua_kafka(topic: str) -> dict:
    """Start the OPC-UA to Kafka bridge for a given topic."""
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "-p", PROJECT_NAME,
             "up", "-d", "opcua-kafka"],
            env={**os.environ, "topic": topic},
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return {"status": "error", "detail": result.stderr}
        return {"status": "started", "topic": topic}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@docker_mcp.tool()
async def stop_opcua_kafka() -> dict:
    """Stop the OPC-UA to Kafka bridge."""
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "-p", PROJECT_NAME,
             "stop", "opcua-kafka"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return {"status": "error", "detail": result.stderr}
        return {"status": "stopped"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    
@docker_mcp.tool()
async def list_opcua_kafka_bridges() -> dict:
    """List all running OPC-UA Kafka bridge containers and their status."""
    try:
        result = subprocess.run(
            ["docker", "ps", "-a",
             "--filter", "name=opcua-kafka",
             "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return {"status": "error", "detail": result.stderr}

        containers = []
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split("\t")
                containers.append({
                    "name": parts[0],
                    "status": parts[1],
                    "image": parts[2]
                })

        return {
            "count": len(containers),
            "bridges": containers
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8087))
    docker_mcp.settings.port = port
    docker_mcp.settings.host = "0.0.0.0"
    docker_mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    docker_mcp.run(transport="streamable-http")
