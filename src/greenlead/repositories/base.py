"""Repository interface for GreenLead data access.

This module defines the abstract contract that all storage backends must
implement. Routes and services depend only on this interface, never on
concrete adapters like Google Sheets.
"""

from abc import ABC, abstractmethod
from typing import Any

from greenlead.models.schemas import (
    AuditEvent,
    Company,
    CompanyCreate,
    Contact,
    ContactCreate,
    FollowUp,
    FollowUpCreate,
    Meeting,
    MeetingCreate,
    ProductEvent,
    User,
    UserCreate,
)


class AuditRepository(ABC):
    """Append-oriented audit trail. There is deliberately no update/delete."""

    @abstractmethod
    def append(self, event: AuditEvent) -> AuditEvent:
        """Persist one audit event."""
        ...

    @abstractmethod
    def list_events(
        self,
        actor: str | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        outcome: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEvent]:
        """Return audit events (newest first) matching the given filters."""
        ...

    @abstractmethod
    def count_events(
        self,
        actor: str | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        outcome: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        """Return the number of matching audit events (for pagination)."""
        ...


class ProductEventRepository(ABC):
    """Product-analytics event store, separate from the audit trail."""

    @abstractmethod
    def append(self, event: ProductEvent) -> ProductEvent:
        """Persist one product event."""
        ...

    @abstractmethod
    def list_events(
        self, name: str | None = None, limit: int = 200
    ) -> list[ProductEvent]:
        """Return product events (newest first), optionally filtered by name."""
        ...

    @abstractmethod
    def count_by_name(self) -> dict[str, int]:
        """Return event counts grouped by event name."""
        ...


class UserRepository(ABC):
    """Abstract interface for user accounts. Password hashes stay in the repo."""

    @abstractmethod
    def count_users(self) -> int:
        """Return the number of user accounts (used for bootstrap detection)."""
        ...

    @abstractmethod
    def list_users(self) -> list[User]:
        """Return all users (without password hashes)."""
        ...

    @abstractmethod
    def get_user(self, user_id: str) -> User | None:
        """Return a single user by ID, or None."""
        ...

    @abstractmethod
    def get_user_by_username(self, username: str) -> User | None:
        """Return a single user by username, or None."""
        ...

    @abstractmethod
    def get_password_hash(self, username: str) -> str | None:
        """Return the stored bcrypt hash for a username, or None. Auth use only."""
        ...

    @abstractmethod
    def create_user(self, data: UserCreate, password_hash: str) -> User:
        """Persist a new user with the given pre-computed hash."""
        ...

    @abstractmethod
    def update_user(self, user_id: str, data: dict[str, Any]) -> User:
        """Update user fields (role/is_active/last_login/...). Raises KeyError."""
        ...


class CompanyRepository(ABC):
    """Abstract interface for company data operations."""

    @abstractmethod
    def list_companies(self, q: str | None = None) -> list[Company]:
        """Return all non-archived companies, optionally filtered by search query q."""
        ...

    @abstractmethod
    def get_company(self, company_id: str) -> Company | None:
        """Return a single company by ID, or None if not found."""
        ...

    @abstractmethod
    def get_company_by_domain(self, domain: str) -> Company | None:
        """Return a company by normalized domain, or None if not found."""
        ...

    @abstractmethod
    def create_company(self, data: CompanyCreate) -> Company:
        """Create a new company and return it with generated ID and timestamps."""
        ...

    @abstractmethod
    def update_company(self, company_id: str, data: dict[str, str]) -> Company:
        """Update specific fields on a company. Raises KeyError if not found."""
        ...


class ContactRepository(ABC):
    """Abstract interface for contact data operations."""

    @abstractmethod
    def list_contacts_by_company(self, company_id: str) -> list[Contact]:
        """Return all contacts belonging to a specific company."""
        ...

    @abstractmethod
    def get_contact(self, contact_id: str) -> Contact | None:
        """Return a single contact by ID, or None if not found."""
        ...

    @abstractmethod
    def create_contact(self, data: ContactCreate) -> Contact:
        """Create a new contact and return it with generated ID and timestamps."""
        ...

    @abstractmethod
    def update_contact(self, contact_id: str, data: dict[str, Any]) -> Contact:
        """Update specific fields on a contact. Raises KeyError if not found."""
        ...

    @abstractmethod
    def delete_contact(self, contact_id: str) -> bool:
        """Delete a contact by ID. Returns True if deleted, False if not found."""
        ...


class FollowUpRepository(ABC):
    """Abstract interface for follow-up task data operations."""

    @abstractmethod
    def list_followups(self, company_id: str | None = None) -> list[FollowUp]:
        """Return follow-ups, optionally filtered to a single company."""
        ...

    @abstractmethod
    def get_followup(self, followup_id: str) -> FollowUp | None:
        """Return a single follow-up by ID, or None if not found."""
        ...

    @abstractmethod
    def create_followup(self, data: FollowUpCreate) -> FollowUp:
        """Create a follow-up and return it with generated ID and timestamps."""
        ...

    @abstractmethod
    def update_followup(self, followup_id: str, data: dict[str, Any]) -> FollowUp:
        """Update specific fields on a follow-up. Raises KeyError if not found."""
        ...

    @abstractmethod
    def delete_followup(self, followup_id: str) -> bool:
        """Delete a follow-up by ID. Returns True if deleted, False if not found."""
        ...


class MeetingRepository(ABC):
    """Abstract interface for meeting data operations."""

    @abstractmethod
    def list_meetings(self, company_id: str | None = None) -> list[Meeting]:
        """Return meetings, optionally filtered to a single company."""
        ...

    @abstractmethod
    def get_meeting(self, meeting_id: str) -> Meeting | None:
        """Return a single meeting by ID, or None if not found."""
        ...

    @abstractmethod
    def create_meeting(self, data: MeetingCreate) -> Meeting:
        """Create a meeting and return it with generated ID and timestamps."""
        ...

    @abstractmethod
    def update_meeting(self, meeting_id: str, data: dict[str, Any]) -> Meeting:
        """Update specific fields on a meeting. Raises KeyError if not found."""
        ...

    @abstractmethod
    def delete_meeting(self, meeting_id: str) -> bool:
        """Delete a meeting by ID. Returns True if deleted, False if not found."""
        ...
