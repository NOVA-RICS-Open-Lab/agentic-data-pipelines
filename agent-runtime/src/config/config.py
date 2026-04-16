import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel
from mcp.server.fastmcp import FastMCP




load_dotenv(override=True)



class Config:
    AAS_BASE_URL=os.getenv("AAS_BASE_URL")
    NEO4J_URI=os.getenv("NEO4J_URI")
    NEO4J_USER=os.getenv("NEO4J_USER")
    NEO4J_PASSWORD=os.getenv("NEO4J_PASSWORD")
    OPENAI_API_KEY=os.getenv("OPENAI_API_KEY")
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

    # AASX folder paths
    AASX_SOURCE_DIR = os.getenv("AASX_SOURCE_DIR", "/AasxServerBlazor/aasxs")
    AASX_AGENT_DIR  = os.getenv("AASX_AGENT_DIR",  "/app/aasxs")

    #Kafka Port:

    KAFKA_PORT = os.getenv("")
    
    OPENAI_CLIENT=AsyncOpenAI(api_key=OPENAI_API_KEY)

    mcp_server_params_list = []

    if MCP_MODE == "http":
        # HTTP Mode
        for url in [MCP_HTTP_URL, MCP_OPCUA_URL, MCP_KAFKA_URL, MCP_MONGO_URL, MCP_DOCKER_URL, MCP_GRAFANA_URL]: # MCP_NODERED_URL, removido
            if url :
                mcp_server_params_list.append({"url": url})
        
    else:
        # Stdio Mode
        mcp_server_params_list.append({
            "command": "python",
            "args": ["-m", "src.mcp.aasx.aasx_server", "--transport", "stdio"],
            "env": {**os.environ, "PYTHONPATH": "/app"},
        })



    MAX_TURNS = 30  ##10
    def get_model(model_name: str):
        if "gpt" in model_name:
            return OpenAIChatCompletionsModel(model=model_name, openai_client=Config.OPENAI_CLIENT)
        else:
            return model_name
    