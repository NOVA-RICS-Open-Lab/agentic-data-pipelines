from agents import Agent
from src.config import Templates, Config


class SearchAgent:
    def __init__(self, name: str, model_name: str):
        self.name = name
        self.model_name = model_name

    def create_agent(self, mcp_tools) -> Agent:
        return Config.OPENAI_CLIENT.agents.create(
            name="ResearchAgent",
            instructions=Templates.apex() + Templates.search_agent(),
            model="gpt-4.1-mini",
            tools=mcp_tools,
        )
