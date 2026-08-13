"""Company business logic service.

Sits between routes and the repository. Routes call service methods.
Service methods call repository interface methods.
No gspread or Google-specific code belongs here.

AUTHORIZATION CONTRACT
----------------------
Methods ending in ``_for(actor, ...)`` apply record-level authorization via
``core.policy`` and are the ONLY methods a route may call. The plain methods
(``list_companies``, ``get_company``, ...) are the unauthorized data layer used
internally and by domain tests — never call them from a route.
"""

import logging

from greenlead.core import policy
from greenlead.models.schemas import Company, CompanyCreate, User
from greenlead.repositories.base import CompanyRepository

logger = logging.getLogger(__name__)


class DuplicateDomainError(Exception):
    """Raised when a company with the same domain already exists."""


class CompanyService:
    def __init__(self, repo: CompanyRepository) -> None:
        self._repo = repo

    # ── Unauthorized data layer (internal / domain tests) ───────────────────

    def list_companies(self, q: str | None = None) -> list[Company]:
        return self._repo.list_companies(q=q)

    def get_company(self, company_id: str) -> Company | None:
        return self._repo.get_company(company_id)

    def create_company(self, data: CompanyCreate) -> Company:
        # Deduplication: reject same domain
        if data.domain:
            existing = self._repo.get_company_by_domain(data.domain)
            if existing:
                raise DuplicateDomainError(
                    f"شركة بنفس الدومين موجودة بالفعل / "
                    f"A company with domain '{data.domain}' already exists."
                )
        company = self._repo.create_company(data)
        logger.info("Company created: %s (%s)", company.name_en, company.id)
        return company

    # ── Authorized API (routes) ─────────────────────────────────────────────

    def list_companies_for(self, actor: User, q: str | None = None) -> list[Company]:
        """Companies the actor may see (employees: only the ones they own)."""
        return policy.filter_visible(actor, self._repo.list_companies(q=q))

    def get_company_for(self, actor: User, company_id: str) -> Company:
        """Fetch one company or raise.

        Raises KeyError when it does not exist and AccessDenied when the actor
        may not see it — the route renders the same page for both, so an
        unauthorized user cannot probe which ids exist.
        """
        company = self._repo.get_company(company_id)
        if company is None:
            raise KeyError(f"Company not found: {company_id}")
        policy.require_view(actor, company.owner_id)
        return company

    def create_company_for(self, actor: User, data: CompanyCreate) -> Company:
        """Create a company owned by the actor."""
        owned = data.model_copy(
            update={"owner_id": actor.id, "created_by_id": actor.id}
        )
        return self.create_company(owned)

    def update_company_for(
        self, actor: User, company_id: str, changes: dict[str, str]
    ) -> Company:
        company = self.get_company_for(actor, company_id)  # enforces view
        policy.require_edit(actor, company.owner_id)
        payload = dict(changes)
        payload["updated_by_id"] = actor.id
        return self._repo.update_company(company_id, payload)

    def reassign_for(self, actor: User, company_id: str, new_owner_id: str) -> Company:
        """Change record ownership. Manager/Admin only."""
        policy.require_reassign(actor)
        company = self._repo.get_company(company_id)
        if company is None:
            raise KeyError(f"Company not found: {company_id}")
        updated = self._repo.update_company(
            company_id, {"owner_id": new_owner_id, "updated_by_id": actor.id}
        )
        logger.info(
            "Company %s reassigned to %s by %s",
            company_id,
            new_owner_id,
            actor.username,
        )
        return updated
