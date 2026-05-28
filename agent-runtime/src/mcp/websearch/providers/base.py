from abc import ABC, abstractmethod


class SearchProvider(ABC):
    """Abstract base for web search providers.

    Two responsibilities:
    - search(): find candidate URLs for a query
    - fetch(): retrieve cleaned text content from a specific URL
    """

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Run a web search.

        Returns a list of dicts, each with:
        - title: page title
        - url: full URL
        - snippet: short excerpt summarizing the page
        - score: relevance score in [0, 1] (1.0 if provider doesn't supply scores)
        """
        ...

    @abstractmethod
    async def fetch(self, url: str) -> dict:
        """
        Fetch and extract clean main-content text from a URL.

        Returns a dict with:
        - url: the URL fetched (after redirects)
        - title: page title (may be empty)
        - content: cleaned plain text
        """
        ...