import os
import sys
import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from src.mcp.websearch.providers import get_provider

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)


websearch_mcp = FastMCP(
    "websearch_server",
    instructions="""
    This server provides web search and content extraction tools for the
    Researcher agent.

    Available tools:
    - web_search(query, max_results): get a ranked list of URLs with snippets.
      Use this first to discover relevant pages.
    - fetch_url(url): retrieve the full cleaned text content of a specific URL.
      Use after web_search when a result looks promising and you need more
      than the snippet.

    Typical workflow:
        1. web_search("confluent-kafka python AdminClient") -> list of results
        2. Pick the most relevant URL from the snippets.
        3. fetch_url(<that url>) -> full page text.
    """,
)


provider = get_provider()


@websearch_mcp.tool()
async def web_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search the web for the given query and return ranked results.

    Each result is a dict with:
    - title: page title
    - url: full URL
    - snippet: short excerpt (~200 chars) summarizing the page
    - score: relevance score (0-1)

    Use this for exploration: when you need to discover what pages exist
    for a topic. After identifying a promising result, call fetch_url(url)
    to retrieve its full content.

    Tips for good queries:
    - Keep queries short (3-8 words).
    - Use specific technical terms (e.g. "confluent-kafka python AdminClient
      create_topic" rather than "how to make a topic in kafka").
    - Include version numbers when relevant.

    Args:
        query: the search query.
        max_results: number of results to return (default 5, max 10).
    """
    logger.info(f"web_search: query={query!r} max_results={max_results}")
    return await provider.search(query, max_results)


@websearch_mcp.tool()
async def fetch_url(url: str) -> dict:
    """
    Fetch and extract the cleaned main text content of a URL.

    Returns a dict with:
    - url: the final URL after any redirects
    - title: page title (may be empty)
    - content: cleaned plain text of the page's main content

    Use this after web_search when you have identified a promising URL and
    need the full content (snippets alone are usually not enough). Do not
    call this on URLs you have not seen in a search result.

    Note: this works on standard server-rendered HTML pages, which covers
    the vast majority of documentation sites. If a page returns empty
    content, it is likely JavaScript-rendered - try a different result.

    Args:
        url: full URL including scheme (must start with http:// or https://).
    """
    logger.info(f"fetch_url: {url}")
    return await provider.fetch(url)

@websearch_mcp.tool()
async def clarify_technical_detail(technology: str, question: str) -> dict:
    """
    Perform a targeted, precise search to clarify a specific technical question 
    or code ambiguity encountered during the generation phase.

    Use this tool when a higher-level agent (e.g., the Generator) encounters an 
    underspecified idiom, configuration rule, or API function signature that blocks 
    confident code output.

    Returns a structured summary of findings directly related to the issue, 
    derived from top relevant technical documentation or source code references.

    Args:
        technology: The name of the target technology (e.g., 'confluent-kafka', 'asyncua').
        question: The narrow, focused question regarding code structure, parameters, 
                  or library behavior (e.g., 'Should producer.flush() be called explicitly after produce?').
    """
    logger.info(f"clarify_technical_detail: technology={technology!r} question={question!r}")
    
    
    optimized_query = f"{technology} {question}"
    
    
    search_results = await provider.search(optimized_query, max_results=3)
    
    return {
        "technology": technology,
        "question": question,
        "optimized_query": optimized_query,
        "raw_findings": search_results
    }


if __name__ == "__main__":
    mode = os.getenv("MCP_CONNECTION_MODE", "http").lower()
    logger.info(f"Starting websearch MCP server in {mode} mode")

    if mode == "http":
        port = int(os.getenv("PORT", 8091))
        logger.info(f"HTTP mode - listening on port {port}")
        websearch_mcp.settings.port = port
        websearch_mcp.settings.host = "0.0.0.0"
        websearch_mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        websearch_mcp.run(transport="streamable-http")
    else:
        logger.info("STDIO mode")
        websearch_mcp.run(transport="stdio")