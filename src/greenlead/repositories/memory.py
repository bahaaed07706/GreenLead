"""In-memory repository implementation for testing and local development.

This implementation stores data in Python dicts and requires no external
services or credentials. It implements the same interfaces
as the Google Sheets adapter.
"""

import uuid
from datetime import UTC, datetime
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
from greenlead.repositories.base import (
    AuditRepository,
    CompanyRepository,
    ContactRepository,
    FollowUpRepository,
    MeetingRepository,
    ProductEventRepository,
    UserRepository,
)


def _normalize_domain(domain: str) -> str:
    """Strip protocol, www prefix, and trailing slash from a domain."""
    d = domain.lower().strip()
    for prefix in ("https://", "http://"):
        d = d.removeprefix(prefix)
    d = d.removeprefix("www.")
    return d.rstrip("/")


def _audit_matches(
    e: AuditEvent,
    actor: str | None,
    action: str | None,
    entity_type: str | None,
    outcome: str | None,
    date_from: str | None,
    date_to: str | None,
) -> bool:
    """Shared filter predicate for the in-memory audit store."""
    if actor and actor.lower() not in e.actor_username.lower():
        return False
    if action and e.action != action:
        return False
    if entity_type and e.entity_type != entity_type:
        return False
    if outcome and e.outcome != outcome:
        return False
    if date_from and e.timestamp[:10] < date_from:
        return False
    return not (date_to and e.timestamp[:10] > date_to)


class InMemoryAuditRepository(AuditRepository):
    """Append-only in-memory audit trail."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> AuditEvent:
        self._events.append(event)
        return event

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
        matched = [
            e
            for e in self._events
            if _audit_matches(
                e, actor, action, entity_type, outcome, date_from, date_to
            )
        ]
        matched.sort(key=lambda e: e.timestamp, reverse=True)
        return matched[offset : offset + limit]

    def count_events(
        self,
        actor: str | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        outcome: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        return sum(
            1
            for e in self._events
            if _audit_matches(
                e, actor, action, entity_type, outcome, date_from, date_to
            )
        )


class InMemoryProductEventRepository(ProductEventRepository):
    """Append-only in-memory product-analytics store."""

    def __init__(self) -> None:
        self._events: list[ProductEvent] = []

    def append(self, event: ProductEvent) -> ProductEvent:
        self._events.append(event)
        return event

    def list_events(
        self, name: str | None = None, limit: int = 200
    ) -> list[ProductEvent]:
        matched = [e for e in self._events if not name or e.name == name]
        matched.sort(key=lambda e: e.timestamp, reverse=True)
        return matched[:limit]

    def count_by_name(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self._events:
            counts[e.name] = counts.get(e.name, 0) + 1
        return counts


class InMemoryUserRepository(UserRepository):
    """Thread-unsafe in-memory store for User accounts."""

    def __init__(self) -> None:
        self._store: dict[str, User] = {}
        self._hashes: dict[str, str] = {}  # user_id -> password_hash

    def count_users(self) -> int:
        return len(self._store)

    def list_users(self) -> list[User]:
        return list(self._store.values())

    def get_user(self, user_id: str) -> User | None:
        return self._store.get(user_id)

    def get_user_by_username(self, username: str) -> User | None:
        for u in self._store.values():
            if u.username == username:
                return u
        return None

    def get_password_hash(self, username: str) -> str | None:
        u = self.get_user_by_username(username)
        return self._hashes.get(u.id) if u else None

    def create_user(self, data: UserCreate, password_hash: str) -> User:
        now = datetime.now(UTC).isoformat()
        user = User(
            id=str(uuid.uuid4()),
            username=data.username,
            name=data.name,
            email=data.email,
            role=data.role,
            created_at=now,
            updated_at=now,
            created_by=data.created_by,
        )
        self._store[user.id] = user
        self._hashes[user.id] = password_hash
        return user

    def update_user(self, user_id: str, data: dict[str, Any]) -> User:
        if user_id not in self._store:
            raise KeyError(f"User '{user_id}' not found")
        updated_dict = self._store[user_id].model_dump()
        for field, value in data.items():
            if value is not None:
                updated_dict[field] = value
        updated_dict["updated_at"] = datetime.now(UTC).isoformat()
        updated = User(**updated_dict)
        self._store[user_id] = updated
        return updated


class InMemoryCompanyRepository(CompanyRepository):
    """Thread-unsafe in-memory store suitable for testing and development."""

    def __init__(self) -> None:
        self._store: dict[str, Company] = {}

    def list_companies(self, q: str | None = None) -> list[Company]:
        companies = [c for c in self._store.values() if c.archived_at is None]
        if q and q.strip():
            query = q.strip().lower()
            companies = [
                c
                for c in companies
                if query in c.name_en.lower()
                or query in c.name_ar.lower()
                or query in c.domain.lower()
            ]
        return companies

    def get_company(self, company_id: str) -> Company | None:
        return self._store.get(company_id)

    def get_company_by_domain(self, domain: str) -> Company | None:
        normalized = _normalize_domain(domain)
        if not normalized:
            return None
        for company in self._store.values():
            if company.domain == normalized:
                return company
        return None

    def create_company(self, data: CompanyCreate) -> Company:
        now = datetime.now(UTC).isoformat()
        company = Company(
            id=str(uuid.uuid4()),
            name_en=data.name_en,
            name_ar=data.name_ar,
            domain=_normalize_domain(data.domain),
            sector=data.sector,
            city=data.city,
            description=data.description,
            owner_id=data.owner_id,
            created_by_id=data.created_by_id,
            created_at=now,
            updated_at=now,
        )
        self._store[company.id] = company
        return company

    def update_company(self, company_id: str, data: dict[str, str]) -> Company:
        if company_id not in self._store:
            raise KeyError(f"Company '{company_id}' not found")
        existing = self._store[company_id]
        updated_dict = existing.model_dump()
        for field, value in data.items():
            if field == "domain":
                value = _normalize_domain(value)
            updated_dict[field] = value
        updated_dict["updated_at"] = datetime.now(UTC).isoformat()
        updated = Company(**updated_dict)
        self._store[company_id] = updated
        return updated


class InMemoryContactRepository(ContactRepository):
    """Thread-unsafe in-memory store for Contact entities."""

    def __init__(self) -> None:
        self._store: dict[str, Contact] = {}

    def list_contacts_by_company(self, company_id: str) -> list[Contact]:
        return [c for c in self._store.values() if c.company_id == company_id]

    def get_contact(self, contact_id: str) -> Contact | None:
        return self._store.get(contact_id)

    def create_contact(self, data: ContactCreate) -> Contact:
        now = datetime.now(UTC).isoformat()
        contact = Contact(
            id=str(uuid.uuid4()),
            company_id=data.company_id,
            name=data.name,
            title=data.title,
            email=data.email,
            phone=data.phone,
            relationship_level=data.relationship_level,
            is_decision_maker=data.is_decision_maker,
            source_url=data.source_url,
            notes=data.notes,
            owner_id=data.owner_id,
            created_by_id=data.created_by_id,
            created_at=now,
            updated_at=now,
        )
        self._store[contact.id] = contact
        return contact

    def update_contact(self, contact_id: str, data: dict[str, Any]) -> Contact:
        if contact_id not in self._store:
            raise KeyError(f"Contact '{contact_id}' not found")
        existing = self._store[contact_id]
        updated_dict = existing.model_dump()
        for field, value in data.items():
            if value is not None:
                updated_dict[field] = value
        updated_dict["updated_at"] = datetime.now(UTC).isoformat()
        updated = Contact(**updated_dict)
        self._store[contact_id] = updated
        return updated

    def delete_contact(self, contact_id: str) -> bool:
        if contact_id in self._store:
            del self._store[contact_id]
            return True
        return False


class InMemoryFollowUpRepository(FollowUpRepository):
    """Thread-unsafe in-memory store for FollowUp entities."""

    def __init__(self) -> None:
        self._store: dict[str, FollowUp] = {}

    def list_followups(self, company_id: str | None = None) -> list[FollowUp]:
        followups = list(self._store.values())
        if company_id:
            followups = [f for f in followups if f.company_id == company_id]
        return followups

    def get_followup(self, followup_id: str) -> FollowUp | None:
        return self._store.get(followup_id)

    def create_followup(self, data: FollowUpCreate) -> FollowUp:
        now = datetime.now(UTC).isoformat()
        followup = FollowUp(
            id=str(uuid.uuid4()),
            company_id=data.company_id,
            contact_id=data.contact_id,
            title=data.title,
            description=data.description,
            due_date=data.due_date,
            priority=data.priority,
            owner=data.owner,
            owner_id=data.owner_id,
            created_by_id=data.created_by_id,
            created_at=now,
            updated_at=now,
        )
        self._store[followup.id] = followup
        return followup

    def update_followup(self, followup_id: str, data: dict[str, Any]) -> FollowUp:
        if followup_id not in self._store:
            raise KeyError(f"FollowUp '{followup_id}' not found")
        existing = self._store[followup_id]
        updated_dict = existing.model_dump()
        for field, value in data.items():
            if value is not None:
                updated_dict[field] = value
        updated_dict["updated_at"] = datetime.now(UTC).isoformat()
        updated = FollowUp(**updated_dict)
        self._store[followup_id] = updated
        return updated

    def delete_followup(self, followup_id: str) -> bool:
        if followup_id in self._store:
            del self._store[followup_id]
            return True
        return False


class InMemoryMeetingRepository(MeetingRepository):
    """Thread-unsafe in-memory store for Meeting entities."""

    def __init__(self) -> None:
        self._store: dict[str, Meeting] = {}

    def list_meetings(self, company_id: str | None = None) -> list[Meeting]:
        meetings = list(self._store.values())
        if company_id:
            meetings = [m for m in meetings if m.company_id == company_id]
        return meetings

    def get_meeting(self, meeting_id: str) -> Meeting | None:
        return self._store.get(meeting_id)

    def create_meeting(self, data: MeetingCreate) -> Meeting:
        now = datetime.now(UTC).isoformat()
        meeting = Meeting(
            id=str(uuid.uuid4()),
            company_id=data.company_id,
            contact_id=data.contact_id,
            subject=data.subject,
            description=data.description,
            meeting_date=data.meeting_date,
            start_time=data.start_time,
            end_time=data.end_time,
            timezone=data.timezone,
            meeting_type=data.meeting_type,
            meeting_url=data.meeting_url,
            location=data.location,
            participants=data.participants,
            agenda=data.agenda,
            reminder_minutes=data.reminder_minutes,
            owner=data.owner,
            owner_id=data.owner_id,
            created_by_id=data.created_by_id,
            created_at=now,
            updated_at=now,
        )
        self._store[meeting.id] = meeting
        return meeting

    def update_meeting(self, meeting_id: str, data: dict[str, Any]) -> Meeting:
        if meeting_id not in self._store:
            raise KeyError(f"Meeting '{meeting_id}' not found")
        existing = self._store[meeting_id]
        updated_dict = existing.model_dump()
        for field, value in data.items():
            if value is not None:
                updated_dict[field] = value
        updated_dict["updated_at"] = datetime.now(UTC).isoformat()
        updated = Meeting(**updated_dict)
        self._store[meeting_id] = updated
        return updated

    def delete_meeting(self, meeting_id: str) -> bool:
        if meeting_id in self._store:
            del self._store[meeting_id]
            return True
        return False
