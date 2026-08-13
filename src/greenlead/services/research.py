"""Research orchestration service."""

import logging

from greenlead.core.config import get_settings
from greenlead.models.schemas import Company
from greenlead.providers.base import AIProvider, ExtractedCompanyProfile, SearchProvider
from greenlead.repositories.base import CompanyRepository

logger = logging.getLogger(__name__)


class ResearchService:
    def __init__(
        self,
        search_provider: SearchProvider,
        ai_provider: AIProvider,
        company_repo: CompanyRepository,
    ) -> None:
        self.search_provider = search_provider
        self.ai_provider = ai_provider
        self.company_repo = company_repo

    def research_company(self, company_id: str) -> ExtractedCompanyProfile:
        company = self.company_repo.get_company(company_id)
        if not company:
            raise KeyError(f"Company not found: {company_id}")

        query_name = company.name_en or company.name_ar
        # The industry keyword is configurable so the research query stays
        # relevant to whatever sector the deployment targets.
        industry = get_settings().org_industry
        query = f"{query_name} {company.domain} official site OR about OR {industry}"
        logger.info("Executing research search for company %s", company_id)

        search_results = self.search_provider.search(query)
        extracted = self.ai_provider.extract_company_profile(query_name, search_results)
        return extracted

    def apply_research(
        self, company_id: str, extracted: ExtractedCompanyProfile
    ) -> Company:
        update_data = {
            "description": extracted.description,
            "sector": extracted.sector,
            "city": extracted.city,
            "products": extracted.products,
            "digital_footprint": extracted.digital_footprint,
            "compliance_status": extracted.compliance_status,
            "verification_status": "verified",
        }
        updated = self.company_repo.update_company(company_id, update_data)
        logger.info("Applied research profiles to company %s", company_id)
        return updated
