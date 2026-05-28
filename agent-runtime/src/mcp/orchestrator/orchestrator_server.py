import asyncio
import logging
import os
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from src.agents.orchestrator import OrchestratorAgent
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#Define a lifespan manager to safely initialize resources on the server's loop
@asynccontextmanager
async def app_lifespan(server: FastMCP):
    logger.info("Orchestrator server starting up: Warming up agent...")
    
    # Initialize the agent exactly once here, safe inside the running server loop
    await orchestrator.initialize()
    logger.info("Orchestrator agent initialized and ready.")
    
    try:
        yield # Server runs and listens for requests here
    finally:
        logger.info("Orchestrator server shutting down...")

# 2. Pass the lifespan to FastMCP
mcp = FastMCP("Orchestrator", lifespan=app_lifespan)

orchestrator = OrchestratorAgent()

@mcp.tool()
async def request_tool_build(technology_name: str) -> str:
    """
    Coordinates the construction of a new MCP server tool for the given technology.
    """
    prompt = f"Build a tool for the following technology: {technology_name}"
    result = ""
    async for token in orchestrator.run(prompt):
        result += token
    
    return result

def main():
    logger.info("Starting Orchestrator MCP server configuration...")

    mode = os.getenv("MCP_CONNECTION_MODE", "stdio").lower()
    port = int(os.getenv("PORT", 8095))

    if mode == "http":
        logger.info(f"Running in HTTP mode on port {port}")
        mcp.settings.port = port
        mcp.settings.host = "0.0.0.0"
        mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        mcp.run(transport="streamable-http")
    else:
        logger.info("Running in STDIO mode")
        mcp.run(transport="stdio")

if __name__ == "__main__":
    main()