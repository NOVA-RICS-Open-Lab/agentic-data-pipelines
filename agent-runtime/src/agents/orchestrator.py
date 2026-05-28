from agents import Agent, Runner, trace # type: ignore
from src.config import Templates, Config
from contextlib import AsyncExitStack
from agents.mcp import MCPServerStdio, MCPServerSse, MCPServerStreamableHttp # type: ignore
from openai.types.responses import ResponseTextDeltaEvent # type: ignore
from src.utils import make_trace_id
import logging
import asyncio

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """Single orchestrator agent coordinating MCP Process Agents."""

    def __init__(self, name: str = "OrchestratorAgent", model_name: str = "gpt-4.1-mini"):  ##gpt-4.1-mini gpt-5-mini
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
            instructions=Templates.orchestrator_agent(),
            model=Config.get_model(self.model_name),
            mcp_servers=mcp_servers,
        )
        return self.agent
    
    async def initialize(self):
        if self.initialized:
            logger.info("Agent already initialized")
            return
        
        logger.info(f"Initializing {self.name}...")
        
        await self.init_mcp()
        
       
        if self.agent is None:
            self.agent = await self.create_agent(self.mcp_servers)
        
        logger.info("Running warm-up prompt...")
        warmup_stream = Runner.run_streamed(
            self.agent,
            input="Respond with 'ready' if you can hear me.",
            max_turns=1,
        )
        
        async for event in warmup_stream.stream_events():
            pass  
        
        logger.info("Warm-up complete")

        self.initialized = True
        logger.info(f"{self.name} initialization complete")
    
    async def init_mcp(self):
        if self.mcp_servers is None:
            await self.mcp_stack.__aenter__()
            self.mcp_servers = []
            
            for params in Config.orchestrator_mcp_params_list:
                server = None
                max_retries = 10
                retry_delay = 5
                
                for attempt in range(max_retries):
                    try:
                        if "url" in params:
                            logger.info(f"Connecting to HTTP MCP server at {params['url']} (Attempt {attempt+1}/{max_retries})")
                            server = await self.mcp_stack.enter_async_context(
                                MCPServerStreamableHttp(
                                    params={"url": params["url"]},
                                    client_session_timeout_seconds=120
                                )
                            )
                            logger.info(f"Successfully connected to HTTP server at {params['url']}")
                        else:
                            logger.info(f"Connecting to STDIO MCP server: {params['command']} (Attempt {attempt+1}/{max_retries})")
                            server = await self.mcp_stack.enter_async_context(
                                MCPServerStdio(
                                    params={
                                        "command": params["command"],
                                        "args": params.get("args", []),
                                        "env": params.get("env", {}),
                                    },
                                    client_session_timeout_seconds=120
                                )
                            )
                            logger.info(f"Successfully connected to STDIO server")
                        
                        if server:
                            self.mcp_servers.append(server)
                            break # Success, move to next server
                            
                    except Exception as e:
                        if attempt < max_retries - 1:
                            logger.warning(f"Connection failed: {e}. Retrying in {retry_delay}s...")
                            await asyncio.sleep(retry_delay)
                        else:
                            logger.error(f"Failed to connect after {max_retries} attempts: {e}")
                            raise e



    async def run(self, prompt: str):
        trace_name = f"{self.name}-working"
        trace_id = make_trace_id(f"{self.name.lower()}")

        
        self.history.append({"role": "user", "content": prompt})

        with trace(trace_name, trace_id=trace_id):
            await self.init_mcp()
            if self.agent is None:
                self.agent = await self.create_agent(self.mcp_servers)

            # prepare input including conversation history
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
