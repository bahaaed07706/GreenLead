"""Phase 5 tests: Research Pipeline abstractions and service."""

from greenlead.core.config import get_settings
from greenlead.models.schemas import CompanyCreate
from greenlead.providers.mock import MockAIProvider, MockSearchProvider
from greenlead.repositories.memory import InMemoryCompanyRepository
from greenlead.services.research import ResearchService


def test_research_pipeline_flow() -> None:
    repo = InMemoryCompanyRepository()
    company = repo.create_company(
        CompanyCreate(name_en="CyberShield", domain="cybershield.sa")
    )

    search = MockSearchProvider()
    ai = MockAIProvider()
    service = ResearchService(search_provider=search, ai_provider=ai, company_repo=repo)

    # The mock profile reports the configured industry, so this assertion
    # tracks the deployment's ORG_INDUSTRY instead of a hardcoded sector.
    expected_sector = get_settings().org_industry

    extracted = service.research_company(company.id)
    assert extracted.sector == expected_sector
    assert len(extracted.sources) > 0

    updated = service.apply_research(company.id, extracted)
    assert updated.verification_status == "verified"
    assert updated.sector == expected_sector
    assert updated.city == "Example City"
