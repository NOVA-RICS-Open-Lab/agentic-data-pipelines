import httpx
from src.config import Config

class MCPClient:
    """
    MCP client connecting to a single FastMCP HTTP server via HTTP.
    Provides async methods to list tools and call tools.
    """

    def __init__(self, url: str | None = None):
        self.url = url or Config.MCP_URL  # e.g., "http://mcp-server:7001/mcp"
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=30)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client:
            await self._client.aclose()
        self._client = None

    async def list_tools(self) -> list[dict]:
        """
        Get all tools exposed by the FastMCP server.
        """
        if not self._client:
            raise RuntimeError("MCPClient must be used as async context manager")
        resp = await self._client.get(f"{self.url}/tools")
        resp.raise_for_status()
        return resp.json()  # Should return a list of tool dicts

    async def call(self, tool_name: str, args: dict | None = None) -> dict:
        """
        Call a specific tool by name with arguments.
        """
        if not self._client:
            raise RuntimeError("MCPClient must be used as async context manager")
        payload = {"args": args or {}}
        resp = await self._client.post(f"{self.url}/tool/{tool_name}", json=payload)
        resp.raise_for_status()
        return resp.json()
