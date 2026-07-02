from agents import Agent, Runner, trace, function_tool # type: ignore
from src.config import Templates, Config
from contextlib import AsyncExitStack
from agents.mcp import MCPServerStdio, MCPServerSse, MCPServerStreamableHttp # type: ignore
from openai.types.responses import ResponseTextDeltaEvent # type: ignore
from src.utils import make_trace_id
from src.a2a.host import create_a2a_app
from src.a2a.client import A2AClient
from src.agents.cards import ORCHESTRATOR_CARD, RESEARCHER_CARD, GENERATOR_CARD, REVIEWER_CARD
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
        self.local_tools: list = []
        self.initialized = False
        
        self.researcher_client = A2AClient(Config.A2A_RESEARCHER_URL)
        self.generator_client = A2AClient(Config.A2A_GENERATOR_URL)
        self.reviewer_client = A2AClient(Config.A2A_REVIEWER_URL)

    async def create_agent(self, mcp_servers) -> Agent:
        self.agent = Agent(
            name=self.name,
            instructions=Templates.orchestrator_agent(),
            model=Config.get_model(self.model_name),
            mcp_servers=mcp_servers,
            tools=self.local_tools,
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

            self.local_tools = []

            # Add A2A Worker Proxy Tools
            @function_tool(
                name_override="research_technology",
                description_override="Search for technical context about a technology. While providing additional context (version, library to use)"
            )
            async def research_technology(tech_name: str, additional_information: str) -> str:
                error = self._check_tool_limit("research_technology")
                if error: return error

                params = {"task": f"Research the following technology: {tech_name}. Helpful information: {additional_information}"}
                result = await self.researcher_client.call("execute_task", params)
                # Researcher returns a string directly
                return result

            @function_tool(
                name_override="clarify",
                description_override="Clarify specific technical details using existing context."
            )
            async def clarify(question: str, existing_context: str) -> str:
                error = self._check_tool_limit("clarify")
                if error: return error

                params = {"task": f"Clarify this question: {question}. Context: {existing_context}"}
                result = await self.researcher_client.call("execute_task", params)
                # Researcher returns a string directly
                return result

            @function_tool(
                name_override="generate_mcp_server",
                description_override="Generate an MCP server implementation from technology context."
            )
            async def generate_mcp_server(context_json: str) -> str:
                error = self._check_tool_limit("generate_mcp_server")
                if error: return error

                params = {"task": f"Generate MCP server for: {context_json}"}
                result = await self.generator_client.call("execute_task", params)
                # Generator returns a string directly
                return result

            @function_tool(
                name_override="review_code",
                description_override="Review the generated MCP server code for safety and correctness."
            )
            async def review_code(file_path: str) -> str:
                error = self._check_tool_limit("review_code")
                if error: return error

                params = {"task": file_path}
                result = await self.reviewer_client.call("execute_task", params)
                # Reviewer returns a string directly
                return result

            self.local_tools.extend([
                research_technology,
                clarify,
                generate_mcp_server,
                review_code,
            ])

    def _check_tool_limit(self, tool_name: str) -> str | None:
        """Helper to prevent infinite tool loops."""
        if getattr(self, "last_tool_called", None) == tool_name:
            self.consecutive_tool_calls += 1
        else:
            self.last_tool_called = tool_name
            self.consecutive_tool_calls = 1
            
        if self.consecutive_tool_calls >= 10:
            logger.warning(f"Guardrail triggered: {tool_name} called {self.consecutive_tool_calls} times.")
            return f"GUARDRAIL ERROR: You have called '{tool_name}' {self.consecutive_tool_calls} times consecutively. This indicates an infinite loop. ABORT YOUR CURRENT TASK IMMEDIATELY AND REPORT FAILURE TO THE USER."
        return None

    async def handle_a2a_task(self, params: dict):
        """Handler for A2A tasks."""
        task = params.get("task")
        if not task:
            return "No task provided"
        
        result = ""
        async for chunk in self.run(task):
            result += chunk
        
        return result

    def get_a2a_app(self):
        """Return a FastAPI app for A2A communication."""
        return create_a2a_app(ORCHESTRATOR_CARD, self.handle_a2a_task)

    async def run(self, prompt: str):
        # Reset tool tracking per task run
        self.last_tool_called = None
        self.consecutive_tool_calls = 0

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
