from agents import Agent, Runner, trace, function_tool
from src.config import Templates, Config
from contextlib import AsyncExitStack
from agents.mcp import MCPServerStdio, MCPServerSse, MCPServerStreamableHttp
from src.a2a.client import A2AClient
from openai.types.responses import ResponseTextDeltaEvent
from src.utils import make_trace_id
import logging
import json

logger = logging.getLogger(__name__)


class SystemAgent:
    """Single generic agent coordinating MCP servers."""

    def __init__(self, name: str = "SystemAgent", model_name: str = "gpt-4.1-mini"):  ##gpt-4.1-mini gpt-5-mini
        self.name = name
        self.agent: Agent | None = None
        self.model_name = model_name
        self.history: list[dict] = []
        self.mcp_stack = AsyncExitStack()
        self.mcp_servers = None
        self.local_tools: list = []
        self.initialized = False
        self.orchestrator_client = A2AClient(Config.A2A_ORCHESTRATOR_URL)

    async def create_agent(self, mcp_servers) -> Agent:
        self.agent = Agent(
            name=self.name,
            instructions=Templates.system_agent(),
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
        
        # Create the agent
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
            self.local_tools = []

            # Local A2A Orchestrator Proxy Tool
            @function_tool(
                name_override="request_tool_build",
                description_override="Coordinates the construction of a new MCP server tool for the given technology. While also providing additional context from the AAS"
            )
            async def request_tool_build(technology_name: str, additional_context: str) -> str:
                params = {"task": f"Build a tool for the following technology: {technology_name}. While keeping in mind the additional context provided by the AAS: {additional_context}"}
                return await self.orchestrator_client.call("execute_task", params)

            self.local_tools.append(request_tool_build)

            
            @function_tool(
            name_override="list_my_capabilities",
            description_override="Returns the definitive list of operational MCP tool namespaces currently connected. Use this before any gap analysis."
            )
            async def list_my_capabilities() -> str:
                namespaces = {}
                if self.mcp_servers:
                    for server in self.mcp_servers:
                        try:
                            tools = await server.list_tools()
                            server_name = getattr(server, "name", str(server))
                            namespaces[server_name] = [t.name for t in tools]
                        except Exception as e:
                            logger.warning(f"Could not list tools for a server: {e}")
                return json.dumps(namespaces, indent=2)

            self.local_tools.append(list_my_capabilities)

            for params in Config.mcp_server_params_list:
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

        # store user message
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
                    yield event.data.delta  # streaming per token

            # append assistant response to history
            self.history.append({"role": "assistant", "content": assistant_text})
