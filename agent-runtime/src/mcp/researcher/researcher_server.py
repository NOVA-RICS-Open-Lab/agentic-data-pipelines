import asyncio
import logging
import os
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from src.agents.researcher import ResearcherAgent
from src.agents.researcher_schema import TechnologyContext
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define a lifespan manager to safely initialize resources on the server's loop
@asynccontextmanager
async def app_lifespan(server: FastMCP):
    logger.info("Researcher server starting up: Warming up agent...")
    
    # Initialize the agent exactly once here, safe inside the running server loop
    await researcher.initialize()
    logger.info("Researcher agent initialized and ready.")
    
    try:
        yield # Server runs and listens for requests here
    finally:
        logger.info("Researcher server shutting down...")

# 2. Pass the lifespan to FastMCP
mcp = FastMCP("Researcher", lifespan=app_lifespan)

researcher = ResearcherAgent()

@mcp.tool()
async def research_technology(tech_name: str) -> str:
    """
    Gathers technology context for a given technology name.
    Returns a JSON string representing TechnologyContext.
    """
    prompt = f"Research the following technology: {tech_name}"
    result = ""
    async for token in researcher.run(prompt):
        result += token
    
    return result

@mcp.tool()
async def clarify(question: str, existing_context: str) -> str:
    """
    Answers a specific clarification question based on existing technology context.
    """
    prompt = f"Given this context: {existing_context}\n\nAnswer this question: {question}"
    result = ""
    async for token in researcher.run(prompt):
        result += token
    
    return result

def main():
    logger.info("Starting Researcher MCP server configuration...")

    mode = os.getenv("MCP_CONNECTION_MODE", "stdio").lower()
    port = int(os.getenv("PORT", 8093))

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
