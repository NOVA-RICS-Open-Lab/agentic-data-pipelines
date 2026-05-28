import os
import logging
from .base import SearchProvider

logger = logging.getLogger(__name__)


def get_provider() -> SearchProvider:
    """Return the configured search provider based on SEARCH_PROVIDER env var."""
    name = os.getenv("SEARCH_PROVIDER", "searxng").lower()
    logger.info(f"Loading search provider: {name}")

    if name == "searxng":
        from .searxng_provider import SearxngProvider
        return SearxngProvider()
    
    # If there's the need to use other providers set up here

    raise ValueError(f"Unknown SEARCH_PROVIDER: {name!r}")