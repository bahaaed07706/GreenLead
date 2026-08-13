"""SQLAlchemy persistence backend.

Implements the same repository contracts as the in-memory adapters, so services
and routes are unchanged. Targets SQLite (local/dev/tests — survives restart)
and PostgreSQL (production) through one code path. Each method uses a short
session with an explicit transaction boundary.
"""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

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
from greenlead.repositories.memory import _normalize_domain
from greenlead.repositories.sql_models import (
    AuditEventORM,
    Base,
    CompanyORM,
    ContactORM,
    FollowUpORM,
    MeetingORM,
    ProductEventORM,
    UserORM,
)

SessionFactory = Callable[[], Session]


def build_engine(database_url: str) -> Engine:
    """Create an Engine for the given URL, with SQLite-safe defaults."""
    connect_args: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
    return create_engine(database_url, connect_args=connect_args, future=True)


def create_all(engine: Engine) -> None:
    """Create tables if absent (used for SQLite/dev; Alembic drives production)."""
    Base.metadata.create_all(engine)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _norm_owner_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Convert empty ownership ids to NULL so FK constraints stay valid."""
    out = dict(data)
    for key in ("owner_id", "created_by_id", "updated_by_id"):
        if key in out and out[key] == "":
            out[key] = None
    return out


# ── Converters (ORM -> domain) ────────────────────────────────────────────────


def _to_user(o: UserORM) -> User:
    return User(
        id=o.id,
        username=o.username,
        name=o.name,
        email=o.email,
        role=o.role,
        is_active=o.is_active,
        last_login=o.last_login,
        created_at=o.created_at,
        updated_at=o.updated_at,
        created_by=o.created_by,
    )


def _to_company(o: CompanyORM) -> Company:
    return Company(
        id=o.id,
        name_en=o.name_en,
        name_ar=o.name_ar,
        domain=o.domain,
        sector=o.sector,
        city=o.city,
        description=o.description,
        products=o.products,
        digital_footprint=o.digital_footprint,
        compliance_status=o.compliance_status,
        fit_score=o.fit_score,
        confidence_score=o.confidence_score,
        created_at=o.created_at,
        updated_at=o.updated_at,
        archived_at=o.archived_at,
        verification_status=o.verification_status,
        owner_id=o.owner_id or "",
        created_by_id=o.created_by_id or "",
        updated_by_id=o.updated_by_id or "",
    )


def _to_contact(o: ContactORM) -> Contact:
    return Contact(
        id=o.id,
        company_id=o.company_id,
        name=o.name,
        title=o.title,
        email=o.email,
        phone=o.phone,
        relationship_level=o.relationship_level,
        is_decision_maker=o.is_decision_maker,
        source_url=o.source_url,
        verification_status=o.verification_status,
        notes=o.notes,
        created_at=o.created_at,
        updated_at=o.updated_at,
        owner_id=o.owner_id or "",
        created_by_id=o.created_by_id or "",
        updated_by_id=o.updated_by_id or "",
    )


def _to_followup(o: FollowUpORM) -> FollowUp:
    return FollowUp(
        id=o.id,
        company_id=o.company_id,
        contact_id=o.contact_id,
        title=o.title,
        description=o.description,
        due_date=o.due_date,
        priority=o.priority,
        status=o.status,
        owner=o.owner,
        outcome=o.outcome,
        completed_at=o.completed_at,
        created_at=o.created_at,
        updated_at=o.updated_at,
        owner_id=o.owner_id or "",
        created_by_id=o.created_by_id or "",
        updated_by_id=o.updated_by_id or "",
    )


def _to_meeting(o: MeetingORM) -> Meeting:
    return Meeting(
        id=o.id,
        company_id=o.company_id,
        contact_id=o.contact_id,
        subject=o.subject,
        description=o.description,
        meeting_date=o.meeting_date,
        start_time=o.start_time,
        end_time=o.end_time,
        timezone=o.timezone,
        meeting_type=o.meeting_type,
        meeting_url=o.meeting_url,
        location=o.location,
        participants=o.participants,
        agenda=o.agenda,
        reminder_minutes=o.reminder_minutes,
        status=o.status,
        outcome=o.outcome,
        followup_action=o.followup_action,
        owner=o.owner,
        created_at=o.created_at,
        updated_at=o.updated_at,
        owner_id=o.owner_id or "",
        created_by_id=o.created_by_id or "",
        updated_by_id=o.updated_by_id or "",
    )


class SqlUserRepository(UserRepository):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._sf = session_factory

    def count_users(self) -> int:
        with self._sf() as s:
            return len(list(s.scalars(select(UserORM.id))))

    def list_users(self) -> list[User]:
        with self._sf() as s:
            return [_to_user(r) for r in s.scalars(select(UserORM))]

    def get_user(self, user_id: str) -> User | None:
        with self._sf() as s:
            o = s.get(UserORM, user_id)
            return _to_user(o) if o else None

    def get_user_by_username(self, username: str) -> User | None:
        with self._sf() as s:
            o = s.scalars(select(UserORM).where(UserORM.username == username)).first()
            return _to_user(o) if o else None

    def get_password_hash(self, username: str) -> str | None:
        with self._sf() as s:
            o = s.scalars(select(UserORM).where(UserORM.username == username)).first()
            return o.password_hash if o else None

    def create_user(self, data: UserCreate, password_hash: str) -> User:
        now = _now()
        with self._sf() as s:
            o = UserORM(
                id=str(uuid.uuid4()),
                username=data.username,
                name=data.name,
                email=data.email,
                password_hash=password_hash,
                role=data.role,
                created_at=now,
                updated_at=now,
                created_by=data.created_by,
            )
            s.add(o)
            s.commit()
            s.refresh(o)
            return _to_user(o)

    def update_user(self, user_id: str, data: dict[str, Any]) -> User:
        with self._sf() as s:
            o = s.get(UserORM, user_id)
            if o is None:
                raise KeyError(f"User '{user_id}' not found")
            for field, value in data.items():
                if value is not None:
                    setattr(o, field, value)
            o.updated_at = _now()
            s.commit()
            s.refresh(o)
            return _to_user(o)


class SqlCompanyRepository(CompanyRepository):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._sf = session_factory

    def list_companies(self, q: str | None = None) -> list[Company]:
        with self._sf() as s:
            stmt = select(CompanyORM).where(CompanyORM.archived_at.is_(None))
            rows = list(s.scalars(stmt))
            if q and q.strip():
                query = q.strip().lower()
                rows = [
                    r
                    for r in rows
                    if query in r.name_en.lower()
                    or query in r.name_ar.lower()
                    or query in r.domain.lower()
                ]
            return [_to_company(r) for r in rows]

    def get_company(self, company_id: str) -> Company | None:
        with self._sf() as s:
            o = s.get(CompanyORM, company_id)
            return _to_company(o) if o else None

    def get_company_by_domain(self, domain: str) -> Company | None:
        normalized = _normalize_domain(domain)
        if not normalized:
            return None
        with self._sf() as s:
            stmt = select(CompanyORM).where(CompanyORM.domain == normalized)
            o = s.scalars(stmt).first()
            return _to_company(o) if o else None

    def create_company(self, data: CompanyCreate) -> Company:
        now = _now()
        with self._sf() as s:
            o = CompanyORM(
                id=str(uuid.uuid4()),
                name_en=data.name_en,
                name_ar=data.name_ar,
                domain=_normalize_domain(data.domain),
                sector=data.sector,
                city=data.city,
                description=data.description,
                owner_id=data.owner_id or None,
                created_by_id=data.created_by_id or None,
                created_at=now,
                updated_at=now,
            )
            s.add(o)
            s.commit()
            s.refresh(o)
            return _to_company(o)

    def update_company(self, company_id: str, data: dict[str, str]) -> Company:
        with self._sf() as s:
            o = s.get(CompanyORM, company_id)
            if o is None:
                raise KeyError(f"Company '{company_id}' not found")
            for field, value in data.items():
                if field == "domain":
                    value = _normalize_domain(value)
                setattr(o, field, value)
            o.updated_at = _now()
            s.commit()
            s.refresh(o)
            return _to_company(o)


class SqlContactRepository(ContactRepository):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._sf = session_factory

    def list_contacts_by_company(self, company_id: str) -> list[Contact]:
        with self._sf() as s:
            stmt = select(ContactORM).where(ContactORM.company_id == company_id)
            return [_to_contact(r) for r in s.scalars(stmt)]

    def get_contact(self, contact_id: str) -> Contact | None:
        with self._sf() as s:
            o = s.get(ContactORM, contact_id)
            return _to_contact(o) if o else None

    def create_contact(self, data: ContactCreate) -> Contact:
        now = _now()
        with self._sf() as s:
            o = ContactORM(
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
                owner_id=data.owner_id or None,
                created_by_id=data.created_by_id or None,
                created_at=now,
                updated_at=now,
            )
            s.add(o)
            s.commit()
            s.refresh(o)
            return _to_contact(o)

    def update_contact(self, contact_id: str, data: dict[str, Any]) -> Contact:
        with self._sf() as s:
            o = s.get(ContactORM, contact_id)
            if o is None:
                raise KeyError(f"Contact '{contact_id}' not found")
            for field, value in _norm_owner_fields(data).items():
                if value is not None or field.endswith("_id"):
                    setattr(o, field, value)
            o.updated_at = _now()
            s.commit()
            s.refresh(o)
            return _to_contact(o)

    def delete_contact(self, contact_id: str) -> bool:
        with self._sf() as s:
            o = s.get(ContactORM, contact_id)
            if o is None:
                return False
            s.delete(o)
            s.commit()
            return True


class SqlFollowUpRepository(FollowUpRepository):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._sf = session_factory

    def list_followups(self, company_id: str | None = None) -> list[FollowUp]:
        with self._sf() as s:
            stmt = select(FollowUpORM)
            if company_id:
                stmt = stmt.where(FollowUpORM.company_id == company_id)
            return [_to_followup(r) for r in s.scalars(stmt)]

    def get_followup(self, followup_id: str) -> FollowUp | None:
        with self._sf() as s:
            o = s.get(FollowUpORM, followup_id)
            return _to_followup(o) if o else None

    def create_followup(self, data: FollowUpCreate) -> FollowUp:
        now = _now()
        with self._sf() as s:
            o = FollowUpORM(
                id=str(uuid.uuid4()),
                company_id=data.company_id,
                contact_id=data.contact_id,
                title=data.title,
                description=data.description,
                due_date=data.due_date,
                priority=data.priority,
                owner=data.owner,
                owner_id=data.owner_id or None,
                created_by_id=data.created_by_id or None,
                created_at=now,
                updated_at=now,
            )
            s.add(o)
            s.commit()
            s.refresh(o)
            return _to_followup(o)

    def update_followup(self, followup_id: str, data: dict[str, Any]) -> FollowUp:
        with self._sf() as s:
            o = s.get(FollowUpORM, followup_id)
            if o is None:
                raise KeyError(f"FollowUp '{followup_id}' not found")
            for field, value in _norm_owner_fields(data).items():
                if value is not None or field.endswith("_id"):
                    setattr(o, field, value)
            o.updated_at = _now()
            s.commit()
            s.refresh(o)
            return _to_followup(o)

    def delete_followup(self, followup_id: str) -> bool:
        with self._sf() as s:
            o = s.get(FollowUpORM, followup_id)
            if o is None:
                return False
            s.delete(o)
            s.commit()
            return True


class SqlMeetingRepository(MeetingRepository):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._sf = session_factory

    def list_meetings(self, company_id: str | None = None) -> list[Meeting]:
        with self._sf() as s:
            stmt = select(MeetingORM)
            if company_id:
                stmt = stmt.where(MeetingORM.company_id == company_id)
            return [_to_meeting(r) for r in s.scalars(stmt)]

    def get_meeting(self, meeting_id: str) -> Meeting | None:
        with self._sf() as s:
            o = s.get(MeetingORM, meeting_id)
            return _to_meeting(o) if o else None

    def create_meeting(self, data: MeetingCreate) -> Meeting:
        now = _now()
        with self._sf() as s:
            o = MeetingORM(
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
                owner_id=data.owner_id or None,
                created_by_id=data.created_by_id or None,
                created_at=now,
                updated_at=now,
            )
            s.add(o)
            s.commit()
            s.refresh(o)
            return _to_meeting(o)

    def update_meeting(self, meeting_id: str, data: dict[str, Any]) -> Meeting:
        with self._sf() as s:
            o = s.get(MeetingORM, meeting_id)
            if o is None:
                raise KeyError(f"Meeting '{meeting_id}' not found")
            for field, value in _norm_owner_fields(data).items():
                if value is not None or field.endswith("_id"):
                    setattr(o, field, value)
            o.updated_at = _now()
            s.commit()
            s.refresh(o)
            return _to_meeting(o)

    def delete_meeting(self, meeting_id: str) -> bool:
        with self._sf() as s:
            o = s.get(MeetingORM, meeting_id)
            if o is None:
                return False
            s.delete(o)
            s.commit()
            return True


def make_session_factory(engine: Engine) -> SessionFactory:
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


class SqlAuditRepository(AuditRepository):
    """Append-oriented audit trail backed by SQL."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sf = session_factory

    def _filtered(
        self,
        actor: str | None,
        action: str | None,
        entity_type: str | None,
        outcome: str | None,
        date_from: str | None,
        date_to: str | None,
    ) -> Any:
        stmt = select(AuditEventORM)
        if actor:
            stmt = stmt.where(AuditEventORM.actor_username.ilike(f"%{actor}%"))
        if action:
            stmt = stmt.where(AuditEventORM.action == action)
        if entity_type:
            stmt = stmt.where(AuditEventORM.entity_type == entity_type)
        if outcome:
            stmt = stmt.where(AuditEventORM.outcome == outcome)
        if date_from:
            stmt = stmt.where(AuditEventORM.timestamp >= date_from)
        if date_to:
            stmt = stmt.where(AuditEventORM.timestamp <= date_to + "T23:59:59")
        return stmt

    def append(self, event: AuditEvent) -> AuditEvent:
        with self._sf() as s:
            s.add(
                AuditEventORM(
                    id=event.id,
                    actor_user_id=event.actor_user_id or None,
                    actor_username=event.actor_username,
                    action=event.action,
                    entity_type=event.entity_type,
                    entity_id=event.entity_id,
                    timestamp=event.timestamp,
                    correlation_id=event.correlation_id,
                    outcome=event.outcome,
                    summary=event.summary,
                    reason=event.reason,
                )
            )
            s.commit()
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
        with self._sf() as s:
            stmt = (
                self._filtered(actor, action, entity_type, outcome, date_from, date_to)
                .order_by(AuditEventORM.timestamp.desc())
                .limit(limit)
                .offset(offset)
            )
            return [
                AuditEvent(
                    id=o.id,
                    actor_user_id=o.actor_user_id or "",
                    actor_username=o.actor_username,
                    action=o.action,
                    entity_type=o.entity_type,
                    entity_id=o.entity_id,
                    timestamp=o.timestamp,
                    correlation_id=o.correlation_id,
                    outcome=o.outcome,
                    summary=o.summary,
                    reason=o.reason,
                )
                for o in s.scalars(stmt)
            ]

    def count_events(
        self,
        actor: str | None = None,
        action: str | None = None,
        entity_type: str | None = None,
        outcome: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> int:
        with self._sf() as s:
            stmt = self._filtered(
                actor, action, entity_type, outcome, date_from, date_to
            )
            return len(list(s.scalars(stmt)))


class SqlProductEventRepository(ProductEventRepository):
    """Product-analytics event store backed by SQL."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._sf = session_factory

    def append(self, event: ProductEvent) -> ProductEvent:
        with self._sf() as s:
            s.add(
                ProductEventORM(
                    id=event.id,
                    name=event.name,
                    user_id=event.user_id or None,
                    timestamp=event.timestamp,
                    properties=event.properties,
                )
            )
            s.commit()
            return event

    def list_events(
        self, name: str | None = None, limit: int = 200
    ) -> list[ProductEvent]:
        with self._sf() as s:
            stmt = select(ProductEventORM)
            if name:
                stmt = stmt.where(ProductEventORM.name == name)
            stmt = stmt.order_by(ProductEventORM.timestamp.desc()).limit(limit)
            return [
                ProductEvent(
                    id=o.id,
                    name=o.name,
                    user_id=o.user_id or "",
                    timestamp=o.timestamp,
                    properties=o.properties,
                )
                for o in s.scalars(stmt)
            ]

    def count_by_name(self) -> dict[str, int]:
        with self._sf() as s:
            counts: dict[str, int] = {}
            for o in s.scalars(select(ProductEventORM)):
                counts[o.name] = counts.get(o.name, 0) + 1
            return counts
