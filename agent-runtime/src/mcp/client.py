from contextlib import AsyncExitStack
from typing import List
from agents.mcp import MCPServerStdio


class MCPClientManager:
    """Manages multiple local MCP servers via stdio."""
    def __init__(self, server_scripts: List[str]):
        self.server_scripts = server_scripts
        self.servers = []
        self.stack = AsyncExitStack()

    async def __aenter__(self):
        self.server = await MCPServerStdio(
            self.server_script,
            client_session_timeout_seconds=self.client_session_timeout_seconds
        ).__aenter__()
        return self.server

    async def __aexit__(self, exc_type, exc, tb):
        if self.server:
            await self.server.__aexit__(exc_type, exc, tb)
            self.server = None

    async def list_all_tools(self):
        tools = []
        for server in self.servers:
            response = await server.list_tools()
            tools.extend(response.tools)
        return tools

    async def call_tool(self, tool_name: str, args: dict):
        for server in self.servers:
            available_tools = await server.list_tools()
            if any(t.name == tool_name for t in available_tools.tools):
                return await server.call_tool(tool_name, args)
        raise ValueError(f"Tool {tool_name} not found on any MCP server")
