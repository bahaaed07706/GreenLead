"""Research data schemas and provider interfaces.

Defines the structure for web search results, extracted research profiles,
and the AI/Search provider abstractions.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    title: str = Field(..., description="Page title")
    url: str = Field(..., description="Source URL")
    content: str = Field(..., description="Extracted snippet or text body")


class ExtractedCompanyProfile(BaseModel):
    description: str = Field(default="", description="Extracted company overview")
    sector: str = Field(default="", description="Identified industry sector")
    city: str = Field(default="", description="Primary headquarters city")
    products: str = Field(default="", description="Key products or services offered")
    digital_footprint: str = Field(
        default="", description="Summary of digital/tech presence"
    )
    compliance_status: str = Field(
        default="", description="Compliance or regulatory notes"
    )
    sources: list[str] = Field(
        default_factory=list, description="URLs used as evidence"
    )


class SearchProvider(ABC):
    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Perform web search and return structured results."""
        ...


class AIProvider(ABC):
    @abstractmethod
    def extract_company_profile(
        self, company_name: str, search_results: list[SearchResult]
    ) -> ExtractedCompanyProfile:
        """Extract structured company profile from raw search text."""
        ...
