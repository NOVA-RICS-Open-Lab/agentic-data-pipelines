import os
import logging
import httpx
import trafilatura
from .base import SearchProvider

logger = logging.getLogger(__name__)

# A realistic browser UA helps with sites that serve different content to bots.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class SearxngProvider(SearchProvider):
    """Search via a self-hosted SearXNG instance; extract content via Trafilatura."""

    def __init__(self):
        # Inside the docker network, SearXNG is reachable as service-name + container port.
        # The container listens on 8100 (set via SEARXNG_PORT in compose).
        self.base_url = os.getenv("SEARXNG_URL", "http://searxng:8100").rstrip("/")
        logger.info(f"SearxngProvider initialized (base_url={self.base_url})")

    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        max_results = max(1, min(max_results, 10))

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.base_url}/search",
                params={"q": query, "format": "json"},
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("results", []) or []
        return [
            {
                "title": r.get("title", "") or "",
                "url": r.get("url", "") or "",
                "snippet": r.get("content", "") or "",
                "score": float(r.get("score", 1.0)) if r.get("score") else 1.0,
            }
            for r in results[:max_results]
        ]

    async def fetch(self, url: str) -> dict:
        if not url or not url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL: {url!r}")

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=20,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
            final_url = str(resp.url)

        content = trafilatura.extract(html) or ""
        meta = trafilatura.extract_metadata(html)
        title = (meta.title if meta and meta.title else "") or ""

        if not content:
            logger.info(f"No content extracted from {final_url} (likely JS-rendered)")

        return {"url": final_url, "title": title, "content": content}