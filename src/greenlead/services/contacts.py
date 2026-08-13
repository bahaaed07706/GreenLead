"""Contact business logic service.

Sits between routes and the repository layer.
Coordinates company relationship validation and contact CRUD operations.

AUTHORIZATION CONTRACT
----------------------
``*_for(actor, ...)`` methods enforce record-level access and are the only ones
routes may call. Contact access derives from the parent Company: whoever may
see the account may see its people.
"""

import logging
from typing import Any

from greenlead.core import policy
from greenlead.models.schemas import Contact, ContactCreate, User
from greenlead.repositories.base import CompanyRepository, ContactRepository

logger = logging.getLogger(__name__)


class ContactService:
    def __init__(
        self,
        contact_repo: ContactRepository,
        company_repo: CompanyRepository,
    ) -> None:
        self._contact_repo = contact_repo
        self._company_repo = company_repo

    def list_contacts(self, company_id: str) -> list[Contact]:
        """List all contacts belonging to a company."""
        return self._contact_repo.list_contacts_by_company(company_id)

    def get_contact(self, contact_id: str) -> Contact | None:
        """Get a single contact by ID."""
        return self._contact_repo.get_contact(contact_id)

    def create_contact(self, data: ContactCreate) -> Contact:
        """Create a contact after verifying parent company exists."""
        company = self._company_repo.get_company(data.company_id)
        if not company:
            raise KeyError(f"Company not found: {data.company_id}")

        if not data.name.strip():
            raise ValueError("Contact name is required.")

        contact = self._contact_repo.create_contact(data)
        logger.info("Contact created: %s for company %s", contact.name, data.company_id)
        return contact

    def update_contact(self, contact_id: str, data: dict[str, Any]) -> Contact:
        """Update an existing contact."""
        existing = self._contact_repo.get_contact(contact_id)
        if not existing:
            raise KeyError(f"Contact not found: {contact_id}")

        updated = self._contact_repo.update_contact(contact_id, data)
        logger.info("Contact updated: %s", contact_id)
        return updated

    def delete_contact(self, contact_id: str) -> bool:
        """Delete a contact by ID."""
        success = self._contact_repo.delete_contact(contact_id)
        if success:
            logger.info("Contact deleted: %s", contact_id)
        return success

    # ── Authorized API (routes) ─────────────────────────────────────────────

    def _parent_owner(self, company_id: str) -> str:
        company = self._company_repo.get_company(company_id)
        return company.owner_id if company else ""

    def list_contacts_for(self, actor: User, company_id: str) -> list[Contact]:
        """Contacts of a company the actor is allowed to see."""
        policy.require_view(actor, self._parent_owner(company_id))
        return self._contact_repo.list_contacts_by_company(company_id)

    def get_contact_for(self, actor: User, contact_id: str) -> Contact:
        contact = self._contact_repo.get_contact(contact_id)
        if contact is None:
            raise KeyError(f"Contact not found: {contact_id}")
        policy.require_view_related(
            actor, contact.owner_id, self._parent_owner(contact.company_id)
        )
        return contact

    def create_contact_for(self, actor: User, data: ContactCreate) -> Contact:
        policy.require_edit(actor, self._parent_owner(data.company_id))
        owned = data.model_copy(
            update={"owner_id": actor.id, "created_by_id": actor.id}
        )
        return self.create_contact(owned)

    def update_contact_for(
        self, actor: User, contact_id: str, data: dict[str, Any]
    ) -> Contact:
        self.get_contact_for(actor, contact_id)  # enforces access
        payload = dict(data)
        payload["updated_by_id"] = actor.id
        return self.update_contact(contact_id, payload)

    def delete_contact_for(self, actor: User, contact_id: str) -> bool:
        self.get_contact_for(actor, contact_id)  # enforces access
        return self.delete_contact(contact_id)
