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

    OPENAI_CLIENT=AsyncOpenAI(api_key=OPENAI_API_KEY)

    mcp_server_params_list = []

    if MCP_MODE == "http":
        # HTTP Mode
        mcp_server_params_list.append({
            "url": MCP_HTTP_URL
        })
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
    