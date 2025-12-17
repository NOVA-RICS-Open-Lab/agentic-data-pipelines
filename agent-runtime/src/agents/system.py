import gradio as gr
from src.utils import css, js, Color, get_model
from src.config import Templates
from src.agents import get_researcher_tool
from agents import Agent, Tool, Runner, trace, gen_trace_id
from agents.mcp import MCPServerStdio
from src.utils import make_trace_id, read_log
from src.agents import writer_agent, ReportData
from contextlib import AsyncExitStack
from mcp_params import trader_mcp_server_params, researcher_mcp_server_params

mapper = {
    "trace": Color.WHITE,
    "agent": Color.CYAN,
    "function": Color.GREEN,
    "generation": Color.YELLOW,
    "response": Color.MAGENTA,
    "account": Color.RED,
}

class SystemAgent:
    def __init__(self, name: str, model_name: str):
        self.name = name
        self.model_name = model_name
    
    async def create_agent(self, trader_mcp_servers, researcher_mcp_servers) -> Agent:
        research_tool = await get_researcher_tool(researcher_mcp_servers, self.model_name)

        self.agent = Agent(
            name=self.name,
            instructions=Templates.system_instructions(self.name),
            model=get_model(self.model_name),
            tools=[research_tool],
            mcp_servers=trader_mcp_servers,
        )
        return self.agent

    async def run_agent(self, trader_mcp_servers, researcher_mcp_servers):
        self.agent = await self.create_agent(trader_mcp_servers, researcher_mcp_servers)
        message = (
            trade_message(self.name, strategy, account)
            if self.do_trade
            else rebalance_message(self.name, strategy, account)
        )
        await Runner.run(self.agent, message, max_turns=30)

    async def run_with_mcp_servers(self):
        async with AsyncExitStack() as stack:
            trader_mcp_servers = [
                await stack.enter_async_context(
                    MCPServerStdio(params, client_session_timeout_seconds=120)
                )
                for params in trader_mcp_server_params
            ]
            async with AsyncExitStack() as stack:
                researcher_mcp_servers = [
                    await stack.enter_async_context(
                        MCPServerStdio(params, client_session_timeout_seconds=120)
                    )
                    for params in researcher_mcp_server_params(self.name)
                ]
                await self.run_agent(trader_mcp_servers, researcher_mcp_servers)

    async def run_with_trace(self):
        trace_name = f"{self.name}-cenas"
        trace_id = make_trace_id(f"{self.name.lower()}")
        with trace(trace_name, trace_id=trace_id):
            await self.run_with_mcp_servers()

    async def run(self):
        try:
            await self.run_with_trace()
        except Exception as e:
            print(f"Error running trader {self.name}: {e}")
        self.do_trade = not self.do_trade
