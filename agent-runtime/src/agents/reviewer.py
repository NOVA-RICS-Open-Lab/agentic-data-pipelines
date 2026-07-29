from agents import Agent, Runner, trace
from src.config import Templates, Config
from contextlib import AsyncExitStack
from agents.mcp import MCPServerStdio, MCPServerSse, MCPServerStreamableHttp
from openai.types.responses import ResponseTextDeltaEvent
from src.utils import make_trace_id
import logging
from src.a2a.host import create_a2a_app
from src.agents.cards import REVIEWER_CARD


##Reviewer tools
from src.agents.schemas.reviewer_schema import ReviewResult   # adjust path to where you put it
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class ReviewerAgent:
    """Single reviewer agent reviewing generated code from the Generator."""

    def __init__(self, name: str = "ReviewerAgent", model_name: str = "gpt-5-mini"):  ##gpt-4.1-mini gpt-5-mini
        self.name = name
        self.agent: Agent | None = None
        self.model_name = model_name
        self.history: list[dict] = []
        self.mcp_stack = AsyncExitStack()
        self.mcp_servers = None
        self.initialized = False

    async def handle_a2a_task(self, params: dict):
        file_path = params.get("task")
        if not file_path:
            return ReviewResult(approved=False, summary="No file path provided").model_dump_json()

        self.history = []   # stateless

        # 1. Read the generated file from the shared volume
        path = Path(file_path)
        if not path.exists():
            return ReviewResult(approved=False, summary=f"File not found: {path}").model_dump_json()
        if path.suffix != ".py":
            return ReviewResult(approved=False, summary=f"Expected a .py file, got: {path.suffix}").model_dump_json()

        code = path.read_text(encoding="utf-8")
        if not code.strip():
            return ReviewResult(approved=False, summary="File is empty.").model_dump_json()

        # 2. Run the reviewer agent on the code
        prompt = f"Review the following MCP server code.\nFile: {path.name}\n\n{code}"
        raw = ""
        async for delta in self.run(prompt):
            raw += delta

        # 3. Validate the agent's output against ReviewResult
        try:
            result = ReviewResult.model_validate_json(raw)
            logger.info(f"Review of '{path.name}': approved={result.approved}, issues={len(result.issues)}")
            return result.model_dump_json()
        except Exception as e:
            logger.error(f"Reviewer produced invalid output: {e}")
            return ReviewResult(approved=False,summary=f"Reviewer produced unparseable output: {e}").model_dump_json()

    def get_a2a_app(self):
        return create_a2a_app(REVIEWER_CARD, self.handle_a2a_task)

    async def create_agent(self, mcp_servers) -> Agent:
        self.agent = Agent(
            name=self.name,
            instructions=Templates.reviewer_agent(),
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
            for params in Config.reviewer_mcp_params_list:
                if "url" in params:
                    logger.info(f"Connecting to HHTP MCP server at {params['url']}")
                    server = await self.mcp_stack.enter_async_context(
                        MCPServerStreamableHttp(
                            params={"url": params["url"],  
                                    },
                            client_session_timeout_seconds=120
                        )
                    )
                    logger.info(f"Successfully connected to HTTP server at {params['url']}")
                else:
                    logger.info(f"Connecting to STDIO MCP server: {params['command']}")
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

                self.mcp_servers.append(server)



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
