"""Mock Search and AI providers for credential-free development and testing."""

from greenlead.core.config import get_settings
from greenlead.providers.base import (
    AIProvider,
    ExtractedCompanyProfile,
    SearchProvider,
    SearchResult,
)


class MockSearchProvider(SearchProvider):
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        return [
            SearchResult(
                title=f"Official About Page for {query}",
                url="https://example.com/about",
                content=f"{query} is a leading provider in its sector, headquartered in Example City.",
            ),
            SearchResult(
                title=f"{query} Services Overview",
                url="https://example.com/services",
                content="Offers consulting, managed services, and cloud solutions.",
            ),
        ]


class MockAIProvider(AIProvider):
    def extract_company_profile(
        self, company_name: str, search_results: list[SearchResult]
    ) -> ExtractedCompanyProfile:
        sources = [res.url for res in search_results]
        return ExtractedCompanyProfile(
            description=f"{company_name} provides professional services and solutions.",
            sector=get_settings().org_industry,
            city="Example City",
            products="Consulting, Managed Services, Cloud Solutions",
            digital_footprint="Active web portal, cloud infrastructure",
            compliance_status="Compliance review candidate",
            sources=sources,
        )
