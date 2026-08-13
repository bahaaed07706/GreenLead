"""Tavily search provider implementation."""

import logging

import httpx

from greenlead.providers.base import SearchProvider, SearchResult

logger = logging.getLogger(__name__)


class TavilySearchError(Exception):
    """Raised when Tavily API fails."""


class TavilySearchProvider(SearchProvider):
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise TavilySearchError("Tavily API key is missing.")
        self.api_key = api_key
        self.endpoint = "https://api.tavily.com/search"

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        payload = {
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "include_answer": False,
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(self.endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
                results = []
                for item in data.get("results", []):
                    results.append(
                        SearchResult(
                            title=item.get("title", ""),
                            url=item.get("url", ""),
                            content=item.get("content", ""),
                        )
                    )
                return results
        except Exception as e:
            logger.error("Tavily search failed: %s", e)
            raise TavilySearchError(f"Tavily API call failed: {e}") from e
