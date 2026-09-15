from agents import Agent, Runner, trace, function_tool # type: ignore
from src.config import Templates, Config
from contextlib import AsyncExitStack
from agents.mcp import MCPServerStdio, MCPServerSse, MCPServerStreamableHttp # type: ignore
from openai.types.responses import ResponseTextDeltaEvent # type: ignore
from src.utils import make_trace_id, inject_verbatim_functions, inject_functions_to_implement
from src.a2a.host import create_a2a_app
from src.a2a.client import A2AClient
from src.agents.cards import ORCHESTRATOR_CARD, RESEARCHER_CARD, GENERATOR_CARD, REVIEWER_CARD
import logging
import asyncio
import json

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    """Single orchestrator agent coordinating MCP Process Agents."""

    # Hard per-task budgets. The orchestrator LLM is told (in its prompt) to wind
    # down and emit an "unapproved" report once these are hit. This is the code
    # backstop - in particular it stops the invalid_syntax -> generate -> invalid_syntax
    # loop, which never calls review and so only trips the consecutive guard slowly.
    MAX_TOTAL_CALLS = {
        "research_technology": 3,
        "clarify": 6,
        "generate_mcp_server": 5,
        "review_code": 5,
    }
    CONSECUTIVE_LIMIT = 6

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

        self.last_tool_called: str | None = None
        self.consecutive_tool_calls = 0
        self.tool_call_counts: dict[str, int] = {}
        self.last_generate_result: dict | None = None
        self.last_review_result: dict | None = None

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
                description_override=(
                    "Search for technical context about a technology. While providing additional context "
                    "(version, library to use). If your task included a VERBATIM_FUNCTIONS section, pass "
                    "its exact contents through in verbatim_functions, unchanged - never paraphrase, "
                    "shorten, or fold it into additional_information. Pass an empty string if there was none."
                )
            )
            async def research_technology(tech_name: str, additional_information: str, verbatim_functions: str, functions_to_implement: str) -> str:
                error = self._check_tool_limit("research_technology")
                if error: return error

                params = {
                    "task": f"Research the following technology: {tech_name}. Helpful information: {additional_information}",
                    "verbatim_functions": verbatim_functions,
                    "functions_to_implement": functions_to_implement,
                }
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
                description_override=(
                    "Generate an MCP server implementation from technology context. If the TechnologyContext "
                    "(or your original task) carries a verbatim_functions value, pass it through here "
                    "unchanged in verbatim_functions - never fold it into context_json prose. Pass an empty string if there is none."
                    
                )
            )
            async def generate_mcp_server(context_json: str, verbatim_functions: str, functions_to_implement: str) -> str:
                error = self._check_tool_limit("generate_mcp_server")
                if error: return error

                params = {
                    "task": f"Generate MCP server for: {context_json}",
                    "verbatim_functions": verbatim_functions,
                    "functions_to_implement": functions_to_implement,
                }
                result = await self.generator_client.call("execute_task", params)
                # Generator returns a JSON string. Keep the last successful one so
                # handle_a2a_task can hand the structured file_path/spec_path back to
                # the SystemAgent (which needs it to raise the deploy candidate).
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, dict) and parsed.get("status") == "success":
                        self.last_generate_result = parsed
                except (TypeError, json.JSONDecodeError):
                    pass
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
                # Reviewer returns a JSON string; keep the last verdict.
                try:
                    parsed = json.loads(result)
                    if isinstance(parsed, dict):
                        self.last_review_result = parsed
                except (TypeError, json.JSONDecodeError):
                    pass
                return result

            self.local_tools.extend([
                research_technology,
                clarify,
                generate_mcp_server,
                review_code,
            ])

    def _check_tool_limit(self, tool_name: str) -> str | None:
        """Backstop against infinite worker loops. Two independent limits, both
        reset per task in run():
          * a per-task TOTAL cap per tool (MAX_TOTAL_CALLS) - catches the
            invalid_syntax -> generate -> invalid_syntax loop that never reaches
            review and so trips the consecutive guard only slowly;
          * a consecutive-identical-call cap (CONSECUTIVE_LIMIT) - catches a tight
            spin on a single tool.
        Both return a message the orchestrator LLM is expected to act on this turn.
        """
        self.tool_call_counts[tool_name] = self.tool_call_counts.get(tool_name, 0) + 1
        cap = self.MAX_TOTAL_CALLS.get(tool_name)
        if cap is not None and self.tool_call_counts[tool_name] > cap:
            logger.warning(
                f"Budget exhausted: {tool_name} called {self.tool_call_counts[tool_name]} times (cap {cap})."
            )
            return (
                f"BUDGET EXHAUSTED: '{tool_name}' has run {self.tool_call_counts[tool_name]} times, past its "
                f"per-task limit of {cap}. STOP now - do NOT call generate_mcp_server, review_code or "
                f"research_technology again. Emit your terminal report this turn with status \"unapproved\": "
                f"include the most recent file_path (if any), the outstanding reviewer issues or syntax error, "
                f"and how many rounds were used."
            )

        if getattr(self, "last_tool_called", None) == tool_name:
            self.consecutive_tool_calls += 1
        else:
            self.last_tool_called = tool_name
            self.consecutive_tool_calls = 1

        if self.consecutive_tool_calls >= self.CONSECUTIVE_LIMIT:
            logger.warning(
                f"Guardrail triggered: {tool_name} called {self.consecutive_tool_calls}x consecutively."
            )
            return (
                f"GUARDRAIL ERROR: '{tool_name}' called {self.consecutive_tool_calls} times in a row - this is "
                f"a loop. ABORT the current task and report status \"failed\": which step looped, and why."
            )
        return None

    async def handle_a2a_task(self, params: dict):
        """Handler for A2A tasks."""
        task = params.get("task")
        if not task:
            return "No task provided"

        task = inject_verbatim_functions(task, params.get("verbatim_functions") or "")
        task = inject_functions_to_implement(task, params.get("functions_to_implement") or "")

        report = ""
        async for chunk in self.run(task):
            report += chunk

        # If a file was generated, return a structured envelope so the caller
        # (SystemAgent) can raise a deploy candidate. The LLM's prose report is
        # kept under "report" for the caller to relay. When nothing was generated
        # (failure before generation) fall back to the prose alone.
        gen = self.last_generate_result
        if gen and gen.get("file_path"):
            approved = bool(self.last_review_result and self.last_review_result.get("approved"))
            return json.dumps({
                "status": "success" if approved else "unapproved",
                "approved": approved,
                "file_path": gen.get("file_path"),
                "spec_path": gen.get("spec_path"),
                "technology": gen.get("technology"),
                "lint_findings": gen.get("lint_findings", []),
                "uncertainties": gen.get("uncertainties", []),
                "reviewer_notes": (self.last_review_result or {}).get("notes_for_human", []),
                "report": report,
            })

        return report

    def get_a2a_app(self):
        """Return a FastAPI app for A2A communication."""
        return create_a2a_app(ORCHESTRATOR_CARD, self.handle_a2a_task)

    async def run(self, prompt: str):
        # Reset tool tracking per task run
        self.last_tool_called = None
        self.consecutive_tool_calls = 0
        self.tool_call_counts = {}
        self.last_generate_result = None
        self.last_review_result = None

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
