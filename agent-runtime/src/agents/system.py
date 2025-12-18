from agents import Agent
from src.config import Templates, Config


class SystemAgent:
    def __init__(self, name: str, model_name: str):
        self.name = name
        self.model_name = model_name

    async def create_agent(self, mcp_tools) -> Agent:
        from src.agents import SearchAgent
        researcher = SearchAgent.create_agent(mcp_tools)

        return Config.OPENAI_CLIENT.agents.create(
            name="SystemAgent",
            instructions=Templates.apex() + Templates.system_agent(),
            model="gpt-4.1-mini",
            handoffs=[researcher],
        )
