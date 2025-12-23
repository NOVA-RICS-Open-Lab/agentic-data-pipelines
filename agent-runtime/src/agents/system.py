from agents import Agent, Runner
from src.config import Templates, Config
from contextlib import AsyncExitStack
from agents.mcp import MCPServerStdio
from openai.types.responses import ResponseTextDeltaEvent


class SystemAgent:
    """Single generic agent coordinating MCP servers."""

    def __init__(self, name: str = "SystemAgent", model_name: str = "gpt-4.1-mini"):
        self.name = name
        self.agent = None
        self.model_name = model_name

    async def create_agent(self, mcp_servers) -> Agent:
        #from src.agents import SearchAgent
        #researcher_instance = SearchAgent(name="ResearchAgent", model_name="gpt-4.1-mini")
        #researcher = researcher_instance.create_agent(mcp_servers=mcp_servers, tool_executor=tool_executor)

        self.agent = Agent(
            name=self.name,
            instructions=Templates.apex() + Templates.system_agent(),
            model=Config.get_model(self.model_name),
            mcp_servers=mcp_servers,
        )
        return self.agent
    
    async def run_with_mcp_servers_streamed(self, prompt: str):
        async with AsyncExitStack() as stack:
            mcp_servers = [
                await stack.enter_async_context(
                    MCPServerStdio(params, client_session_timeout_seconds=120)
                )
                for params in Config.mcp_server_params_list
            ]

            agent = await self.create_agent(mcp_servers)

            stream = Runner.run_streamed(
                agent,
                input=prompt,
                max_turns=5,
            )

            async for event in stream.stream_events():
                if (
                    event.type == "raw_response_event"
                    and isinstance(event.data, ResponseTextDeltaEvent)
                ):
                    yield event.data.delta
