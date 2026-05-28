import asyncio
import logging
import os
from pathlib import Path
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from src.agents.generator import GeneratorAgent
from src.agents.schemas.generator_schema import GenerationPlan
from src.agents.researcher_schema import TechnologyContext
from src.generator.renderer import Renderer
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define a lifespan manager to safely initialize resources on the server's loop
@asynccontextmanager
async def app_lifespan(server: FastMCP):
    logger.info("Generator server starting up: Warming up agent...")
    
    # Initialize the agent exactly once here, safe inside the running server loop
    await generator.initialize()
    logger.info("Generator agent initialized and ready.")
    
    try:
        yield # Server runs and listens for requests here
    finally:
        logger.info("Generator server shutting down...")

# 2. Pass the lifespan to FastMCP
mcp = FastMCP("Generator", lifespan=app_lifespan)

generator = GeneratorAgent()
renderer = Renderer()

@mcp.tool()
async def generate_mcp_server(context_json: str) -> str:
    """
    Generates an MCP server based on the provided technology context.
    Returns either the path to the generated file or a JSON object with clarification questions.
    """
    prompt = f"Generate an MCP server for this context: {context_json}"
    result_json = ""
    async for token in generator.run(prompt):
        result_json += token
    
    try:
        plan = GenerationPlan.model_validate_json(result_json)
        
        if plan.clarification_questions:
            return json.dumps({
                "status": "clarification_needed",
                "questions": plan.clarification_questions
            })
        
        # Determine output directory (e.g., generated/<tech>)
        output_dir = Path("generated") / plan.technology_lower
        output_path = renderer.render(plan, output_dir)
        
        return json.dumps({
            "status": "success",
            "file_path": str(output_path),
            "technology": plan.technology_pascal
        })
        
    except Exception as e:
        logger.error(f"Failed to parse or render generation plan: {e}")
        return json.dumps({
            "status": "error",
            "message": str(e),
            "raw_result": result_json
        })

def main():
    logger.info("Starting Generator MCP server configuration...")

    mode = os.getenv("MCP_CONNECTION_MODE", "stdio").lower()
    port = int(os.getenv("PORT", 8094))

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
