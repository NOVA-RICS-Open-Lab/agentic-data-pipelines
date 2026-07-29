import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
import anthropic
from agents import OpenAIChatCompletionsModel
from mcp.server.fastmcp import FastMCP




load_dotenv(override=True)



class Config:
    AAS_BASE_URL=os.getenv("AAS_BASE_URL")
    NEO4J_URI=os.getenv("NEO4J_URI")
    NEO4J_USER=os.getenv("NEO4J_USER")
    NEO4J_PASSWORD=os.getenv("NEO4J_PASSWORD")
    OPENAI_API_KEY=os.getenv("OPENAI_API_KEY")
    CLAUDE_API_KEY=os.getenv("CLAUDE_API_KEY")
    MCP_MODE = os.getenv("MCP_CONNECTION_MODE", "stdio").lower()
    MCP_HTTP_URL = os.getenv("MCP_HTTP_URL", "http://aasx-mcp-service:8080/mcp")
    
    MCP_OPCUA_URL = os.getenv("MCP_OPCUA_URL", "http://opcua-mcp-service:8082/mcp")
    MCP_KAFKA_URL = os.getenv("MCP_KAFKA_URL", "http://kafka-mcp-service:8084/mcp")
    MCP_MONGO_URL = os.getenv("MCP_MONGO_URL", "http://mongo-mcp-service:8085/mcp")
    MCP_NODERED_URL = os.getenv("MCP_NODERED_URL", "http://node-red-mcp-service:8086/mcp")
    MCP_DOCKER_URL = os.getenv("MCP_DOCKER_URL", "http://docker-mcp-service:8087/mcp")
    MCP_GRAFANA_URL = os.getenv("MCP_GRAFANA_URL", "http://grafana-mcp-service:8089/mcp")
    GRAFANA_URL = os.getenv("GRAFANA_URL")
    GRAFANA_PASSWORD = os.getenv("GRAFANA_AGENT_TOKEN")

    MCP_RESEARCHER_URL = os.getenv("MCP_RESEARCHER_URL", "http://websearch-mcp-service:8091/mcp")
    MCP_RESEARCH_AGENT_URL = os.getenv("MCP_RESEARCH_AGENT_URL", "http://research-mcp-service:8093/mcp")
    MCP_GENERATOR_AGENT_URL = os.getenv("MCP_GENERATOR_AGENT_URL", "http://generator-mcp-service:8094/mcp")
    MCP_ORCHESTRATOR_AGENT_URL = os.getenv("MCP_ORCHESTRATOR_AGENT_URL", "http://orchestrator-mcp-service:8095/mcp")

    A2A_RESEARCHER_URL = os.getenv("A2A_RESEARCHER_URL", f"http://research-mcp-service:8093/a2a")
    A2A_GENERATOR_URL = os.getenv("A2A_GENERATOR_URL", f"http://generator-mcp-service:8094/a2a")
    
    A2A_ORCHESTRATOR_URL = os.getenv("A2A_ORCHESTRATOR_URL", f"http://orchestrator-mcp-service:8095/a2a")
    A2A_REVIEWER_URL = os.getenv("A2A_REVIEWER_URL", f"http://reviewer-mcp-service:8096/a2a")


    # AASX folder paths
    AASX_SOURCE_DIR = os.getenv("AASX_SOURCE_DIR", "/AasxServerBlazor/aasxs")
    AASX_AGENT_DIR  = os.getenv("AASX_AGENT_DIR",  "/app/aasxs")

    #Kafka Port:

    KAFKA_PORT = os.getenv("")
    
    OPENAI_CLIENT=AsyncOpenAI(api_key=OPENAI_API_KEY)
    CLAUDE_CLIENT=AsyncOpenAI(api_key=CLAUDE_API_KEY, base_url="https://api.anthropic.com/v1/",)
    print("CLAUDE key loaded:", bool(CLAUDE_API_KEY), "prefix:", (CLAUDE_API_KEY or "")[:7])

    mcp_server_params_list = []
    researcher_mcp_params_list = [{"url": MCP_RESEARCHER_URL}]
    orchestrator_mcp_params_list = []
    generator_mcp_params_list = []
    reviewer_mcp_params_list = []

    if MCP_MODE == "http":
        # HTTP Mode
        for url in [MCP_HTTP_URL, MCP_OPCUA_URL, MCP_MONGO_URL, MCP_DOCKER_URL, MCP_GRAFANA_URL]:  ##MCP_KAFKA_URL
            if url :
                mcp_server_params_list.append({"url": url})
        
        orchestrator_mcp_params_list = []
    else:
        # Stdio Mode
        mcp_server_params_list.append({
            "command": "python",
            "args": ["-m", "src.mcp.aasx.aasx_server", "--transport", "stdio"],
            "env": {**os.environ, "PYTHONPATH": "/app"},
        })



    MAX_TURNS = 30  ##10
    @staticmethod
    def get_model(model_name: str):
        if "gpt" in model_name:
            return OpenAIChatCompletionsModel(model=model_name, openai_client=Config.OPENAI_CLIENT)
        if "claude" in model_name:
            return OpenAIChatCompletionsModel(model=model_name, openai_client=Config.CLAUDE_CLIENT)
        else:
            return model_name
