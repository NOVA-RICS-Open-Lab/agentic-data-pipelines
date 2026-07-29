from agents import Agent, Runner, trace
from src.config import Templates, Config
from contextlib import AsyncExitStack
from agents.mcp import MCPServerStdio, MCPServerSse, MCPServerStreamableHttp
from openai.types.responses import ResponseTextDeltaEvent
from src.utils import make_trace_id
import logging
from src.a2a.host import create_a2a_app
from src.agents.cards import GENERATOR_CARD

##Rendered part
from src.agents.schemas.generator_schema import GenerationPlan
from src.generator.renderer import Renderer
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class GeneratorAgent:
    """Single generator agent making MCP Tools."""

    def __init__(self, name: str = "GeneratorAgent", model_name: str = "claude-opus-4-8"):  ##gpt-4.1-mini gpt-5-mini
        self.name = name
        self.agent: Agent | None = None
        self.model_name = model_name
        self.history: list[dict] = []
        self.mcp_stack = AsyncExitStack()
        self.mcp_servers = None
        self.initialized = False
        self.renderer = Renderer()

    async def handle_a2a_task(self, params: dict):
        task = params.get("task")
        if not task:
            return "No task provided"

        self.history = []   #Clean history each task

        result_json = ""
        async for token in self.run(task):
            result_json += token
        
        try:
            plan = GenerationPlan.model_validate_json(result_json)
            
            if plan.clarification_questions:
                return json.dumps({
                    "status": "clarification_needed",
                    "questions": plan.clarification_questions
                })
            
            # Determine output directory (e.g., generated/<tech>)
            output_dir = Path("generated") / plan.technology_lower
            output_path = self.renderer.render(plan, output_dir)
            
            return json.dumps({
                "status": "success",
                "file_path": str(output_path),
                "technology": plan.technology_pascal
            })
            
        except Exception as e:
            logger.error(f"Failed to parse or render generation plan: {e}")
            return json.dumps({
                "status": "error",
                "message": str(e),
                "raw_result": result_json
            })


    def get_a2a_app(self):
        return create_a2a_app(GENERATOR_CARD, self.handle_a2a_task)

    async def create_agent(self, mcp_servers) -> Agent:
        self.agent = Agent(
            name=self.name,
            instructions=Templates.generator_agent(),
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
            for params in Config.generator_mcp_params_list:
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
                # if event.type == "raw_response_event" and isinstance(
                #     event.data, ResponseTextDeltaEvent
                # ):
                #     assistant_text += event.data.delta
                #     yield event.data.delta  
                pass
            assistant_text = stream.final_output or ""
            yield assistant_text
            

            
            self.history.append({"role": "assistant", "content": assistant_text})
