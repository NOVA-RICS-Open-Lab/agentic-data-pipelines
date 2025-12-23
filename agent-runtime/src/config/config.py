import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
from agents import OpenAIChatCompletionsModel

load_dotenv(override=True)

class Config:
    AAS_BASE_URL=os.getenv("AAS_BASE_URL")
    NEO4J_URI=os.getenv("NEO4J_URI")
    NEO4J_USER=os.getenv("NEO4J_USER")
    NEO4J_PASSWORD=os.getenv("NEO4J_PASSWORD")
    OPENAI_API_KEY=os.getenv("OPENAI_API_KEY")
    MCP_URL=os.getenv("MCP_URL")

    OPENAI_CLIENT=AsyncOpenAI(api_key=OPENAI_API_KEY)

    servers = [
        "src/mcp/server.py"
    ]

    mcp_server_params_list = [
        
    ]

    def get_model(model_name: str):
        if "gpt" in model_name:
            return OpenAIChatCompletionsModel(model=model_name, openai_client=Config.OPENAI_CLIENT)
        else:
            return model_name
    