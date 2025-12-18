from dotenv import load_dotenv
import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from mcp.server.fastmcp import FastMCP
import os
import uvicorn
from starlette.middleware.cors import CORSMiddleware

load_dotenv(override=True)

mcp = FastMCP("Agentic MCP Server")

def _extract_text(html: str) -> str:
    try:
        return md(html, strip=["script", "style"])
    except Exception:
        soup = BeautifulSoup(html, "html.parser")
        for s in soup(["script", "style"]):
            s.decompose()
        return soup.get_text("\n", strip=True)

@mcp.tool()
async def web_search(query: str, max_results: int = 5) -> list[dict]:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            "https://duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0"},
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        return [
            {"title": a.get_text(strip=True), "url": a.get("href")}
            for a in soup.select("a.result__a")[:max_results]
        ]

@mcp.tool()
async def fetch_url(url: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return {
            "url": url,
            "markdown": _extract_text(r.text)[:40000],
        }

# main.py
def main():
    print("Say Hello MCP Server starting...")
    
    # Setup Starlette app with CORS for cross-origin requests
    app = mcp.streamable_http_app()
    
    # IMPORTANT: add CORS middleware for browser based clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id", "mcp-protocol-version"],
        max_age=86400,
    )

    # Get port from environment variable (Smithery sets this to 8081)
    port = int(os.environ.get("MCP_PORT", 7001))
    print(f"Listening on port {port}")

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="debug")

if __name__ == "__main__":
    main()