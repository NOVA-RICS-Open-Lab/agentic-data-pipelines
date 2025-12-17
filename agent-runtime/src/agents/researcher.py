from agents import Agent, Tool
from src.config import Templates
from src.utils.llms import get_model

async def get_researcher_agent(mcp_servers, model_name) -> Agent:
    researcher = Agent(
        name="Researcher",
        instructions=Templates.researcher_instructions(),
        model=get_model(model_name),
        mcp_servers=mcp_servers,
    )
    return researcher

async def get_researcher_tool(mcp_servers, model_name) -> Tool:
    researcher = await get_researcher_agent(mcp_servers, model_name)
    return researcher.as_tool(tool_name="Researcher", tool_description=Templates.research_tool())
