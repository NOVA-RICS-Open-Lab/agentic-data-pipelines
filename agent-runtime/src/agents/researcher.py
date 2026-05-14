from agents import Agent, Runner, trace
from src.config import Templates, Config
from contextlib import AsyncExitStack
from agents.mcp import MCPServerStreamableHttp
from openai.types.responses import ResponseTextDeltaEvent
from src.utils import make_trace_id
import logging
from src.agents.researcher_schema import TechnologyContext
logger = logging.getLogger(__name__)


class ResearcherAgent:
    """Agent that gathers technology context for the Generator."""

    def __init__(self, name: str = "ResearcherAgent", model_name: str = "gpt-4.1-mini"):
        self.name = name
        self.agent: Agent | None = None
        self.model_name = model_name
        self.history: list[dict] = []
        self.mcp_stack = AsyncExitStack()
        self.mcp_servers = None
        self.initialized = False

    async def create_agent(self, mcp_servers) -> Agent:
        self.agent = Agent(
            name=self.name,
            instructions=Templates.researcher_agent(),
            model=Config.get_model(self.model_name),
            mcp_servers=mcp_servers,
            output_type=TechnologyContext,
        )
        return self.agent

    async def initialize(self):
        if self.initialized:
            return
        logger.info(f"Initializing {self.name}...")
        await self.init_mcp()
        if self.agent is None:
            self.agent = await self.create_agent(self.mcp_servers)
        self.initialized = True

    async def init_mcp(self):
        if self.mcp_servers is not None:
            return
        await self.mcp_stack.__aenter__()
        self.mcp_servers = []
        for params in Config.researcher_mcp_params_list:
            logger.info(f"Connecting to HTTP MCP server at {params['url']}")
            server = await self.mcp_stack.enter_async_context(
                MCPServerStreamableHttp(
                    params={"url": params["url"]},
                    client_session_timeout_seconds=120,
                )
            )
            logger.info(f"Connected to {params['url']}")
            self.mcp_servers.append(server)

    async def run(self, prompt: str):
        trace_id = make_trace_id(f"{self.name.lower()}")
        self.history.append({"role": "user", "content": prompt})

        with trace(f"{self.name}-working", trace_id=trace_id):
            await self.init_mcp()
            if self.agent is None:
                self.agent = await self.create_agent(self.mcp_servers)

            conversation_input = "\n".join(
                f'{msg["role"]}: {msg["content"]}' for msg in self.history
            )

            stream = Runner.run_streamed(
                self.agent,
                input=conversation_input,
                max_turns=Config.MAX_TURNS,
            )

            assistant_text = ""
            async for event in stream.stream_events():
                if event.type == "raw_response_event" and isinstance(
                    event.data, ResponseTextDeltaEvent
                ):
                    assistant_text += event.data.delta
                    yield event.data.delta

            self.history.append({"role": "assistant", "content": assistant_text})