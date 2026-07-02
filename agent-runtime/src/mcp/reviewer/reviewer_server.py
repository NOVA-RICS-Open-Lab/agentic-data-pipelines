import asyncio
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from src.agents.reviewer import ReviewerAgent
from src.agents.schemas.reviewer_schema import ReviewIssue, ReviewResult
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define a lifespan manager to safely initialize resources on the server's loop
@asynccontextmanager
async def app_lifespan(server: FastMCP):
    logger.info("Reviewer server starting up: Warming up agent...")
    
    # Initialize the agent exactly once here, safe inside the running server loop
    await reviewer.initialize()
    logger.info("Reviewer agent initialized and ready.")
    
    try:
        yield # Server runs and listens for requests here
    finally:
        logger.info("Reviewer server shutting down...")

# 2. Pass the lifespan to FastMCP
mcp = FastMCP("ReviewerAgent", lifespan=app_lifespan)

reviewer = ReviewerAgent()

## TO DO:

@mcp.tool()
async def review_mcp_server(output_path_from_generator: str) -> str:
    """
    Reviews the code generator for a new mcp server from the GeneratorAgent
    Args:
    file_path: Absolute or relative path to the generated Python file
    """
    
    path = Path(output_path_from_generator)

    if not path.exists():
        return ReviewResult(
            approved=False,
            summary=f"File not found: {path}"
        ).model_dump_json()

    if path.suffix != ".py":
        return ReviewResult(
            approved=False,
            summary=f"Expected a .py file, got: {path.suffix}"
        ).model_dump_json()

    code_to_review = path.read_text(encoding="utf-8")

    if not code_to_review.strip():
        return ReviewResult(
            approved=False,
            summary="File is empty."
        ).model_dump_json()

    prompt = f"""

    Review the following Python MCP server code.
    File: {path.name}"""
    
    try: 
        raw_response = ""
        async for token in reviewer.run(prompt):
            raw_response += token
        
        result = ReviewResult.model_validate_json(raw_response)
        logger.info(f"Review of '{path.name}': approved={result.approved}")
        return result.model_dump_json()
    except Exception as e:
        logger.error(f"ReviewerAgent failed: {e}")
        return ReviewResult(approved=False, summary=f"Reviewer agent error: {str(e)}").model_dump_json()
    

def main():
    logger.info("Starting Generator MCP server configuration...")

    mode = os.getenv("MCP_CONNECTION_MODE", "stdio").lower()
    port = int(os.getenv("PORT", 8096))

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
