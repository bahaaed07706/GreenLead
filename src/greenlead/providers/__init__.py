"""Provider factory for search and AI abstractions."""

from greenlead.core.config import get_settings
from greenlead.providers.base import AIProvider, SearchProvider
from greenlead.providers.mock import MockAIProvider, MockSearchProvider
from greenlead.providers.tavily import TavilySearchProvider


def get_search_provider() -> SearchProvider:
    settings = get_settings()
    if settings.tavily_api_key:
        return TavilySearchProvider(settings.tavily_api_key)
    return MockSearchProvider()


def get_ai_provider() -> AIProvider:
    # Future OpenAI/Gemini bindings will check settings here
    return MockAIProvider()
