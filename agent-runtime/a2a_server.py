import os
import logging
import json
from src.agents import OrchestratorAgent, ResearcherAgent, GeneratorAgent, ReviewerAgent
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from src.a2a.models import JSONRPCRequest, JSONRPCResponse
from fastapi import Request
from starlette.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_mcp_server(agent_type: str, agent):
    """Creates a legacy MCP server for the agent and adds A2A endpoints."""
    mcp = FastMCP(agent_type.capitalize())

    # --- Legacy MCP Tools ---
    if agent_type == "orchestrator":
        @mcp.tool()
        async def request_tool_build(technology_name: str) -> str:
            """Coordinates the construction of a new MCP server tool."""
            prompt = f"Build a tool for the following technology: {technology_name}"
            result = ""
            async for token in agent.run(prompt):
                result += token
            return result
    
    elif agent_type == "researcher":
        @mcp.tool()
        async def research_technology(tech_name: str) -> str:
            """Gathers technology context for a given technology name."""
            prompt = f"Research the following technology: {tech_name}"
            result = ""
            async for token in agent.run(prompt):
                result += token
            return result
        
        @mcp.tool()
        async def clarify(question: str, existing_context: str) -> str:
            """Answers a specific clarification question."""
            prompt = f"Given this context: {existing_context}\n\nAnswer this question: {question}"
            result = ""
            async for token in agent.run(prompt):
                result += token
            return result
        
    elif agent_type == "generator":
        @mcp.tool()
        async def generate_mcp_server(context_json: str) -> str:
            """Generates an MCP server based on the provided technology context."""
            prompt = f"Generate an MCP server for this context: {context_json}"
            result_json = ""
            async for token in agent.run(prompt):
                result_json += token
            return result_json

    # --- A2A Protocol Endpoints (JSON-RPC over HTTP) ---
    # We use custom_route to expose A2A endpoints on the same port
    
    @mcp.custom_route("/a2a/info", methods=["GET"])
    async def a2a_info(request: Request):
        # Get the card from the agent instance
        from src.agents.cards import ORCHESTRATOR_CARD, RESEARCHER_CARD, GENERATOR_CARD, REVIEWER_CARD
        cards = {
            "orchestrator": ORCHESTRATOR_CARD,
            "researcher": RESEARCHER_CARD,
            "generator": GENERATOR_CARD,
            "reviewer": REVIEWER_CARD
        }
        return JSONResponse(cards.get(agent_type, {}))

    @mcp.custom_route("/a2a/rpc", methods=["POST"])
    async def a2a_rpc(request: Request):
        body = await request.json()
        rpc_request = JSONRPCRequest.model_validate(body)
        
        logger.info(f"A2A RECV <- RPC Method: {rpc_request.method} | ID: {rpc_request.id}")
        
        # Call the agent's task handler
        # All agents now have a handle_a2a_task method from previous migration
        result = await agent.handle_a2a_task(rpc_request.params)
        
        response = JSONRPCResponse(result=result, id=rpc_request.id)
        logger.info(f"A2A SEND -> RPC Response | ID: {response.id}")
        
        return JSONResponse(response.model_dump())

    return mcp

def main():
    agent_type = os.getenv("AGENT_TYPE", "orchestrator").lower()
    mcp_port = int(os.getenv("PORT", 8095))
    
    # Initialize the specific agent
    if agent_type == "orchestrator":
        agent = OrchestratorAgent()
    elif agent_type == "researcher":
        agent = ResearcherAgent()
    elif agent_type == "generator":
        agent = GeneratorAgent()
    elif agent_type == "reviewer":
        agent = ReviewerAgent()
    else:
        raise ValueError(f"Unknown AGENT_TYPE: {agent_type}")
    
    logger.info(f"Initializing {agent_type} agent...")
    
    # Create the unified MCP server (with A2A routes)
    mcp = get_mcp_server(agent_type, agent)
    
    # Configure and run using mcp.run()
    mcp.settings.port = mcp_port
    mcp.settings.host = "0.0.0.0"
    mcp.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    
    logger.info(f"Starting {agent_type} Unified Server (MCP + A2A) on port {mcp_port}")
    
    mcp.run(transport="streamable-http")

if __name__ == "__main__":
    main()
