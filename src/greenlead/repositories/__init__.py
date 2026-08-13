"""Repository package.

Provides the abstract repository interfaces and concrete adapters plus a factory
that selects the backend by configuration:

    DATABASE_URL set        -> SQL backend (SQLite locally, PostgreSQL in prod),
                               data survives restart. Preferred production store.
    Google Sheets configured -> Sheets adapter (Company/Contact only; MVP /
                               import-export transition).
    neither                  -> in-memory (data lost on restart; dev/tests).
"""

from collections.abc import Callable
from typing import TYPE_CHECKING

from greenlead.core.config import get_settings
from greenlead.repositories.base import (
    AuditRepository,
    CompanyRepository,
    ContactRepository,
    FollowUpRepository,
    MeetingRepository,
    ProductEventRepository,
    UserRepository,
)
from greenlead.repositories.memory import (
    InMemoryAuditRepository,
    InMemoryCompanyRepository,
    InMemoryContactRepository,
    InMemoryFollowUpRepository,
    InMemoryMeetingRepository,
    InMemoryProductEventRepository,
    InMemoryUserRepository,
)

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.orm import Session

# Module-level singletons for the application lifetime
_user_repo_instance: UserRepository | None = None
_audit_repo_instance: AuditRepository | None = None
_product_event_repo_instance: ProductEventRepository | None = None
_company_repo_instance: CompanyRepository | None = None
_contact_repo_instance: ContactRepository | None = None
_followup_repo_instance: FollowUpRepository | None = None
_meeting_repo_instance: MeetingRepository | None = None

# Shared SQL engine/session factory (built once when DATABASE_URL is set)
_engine: "Engine | None" = None
_session_factory: "Callable[[], Session] | None" = None


def _get_session_factory() -> "Callable[[], Session] | None":
    """Build (once) and return the SQL session factory, or None if no DATABASE_URL."""
    global _engine, _session_factory
    settings = get_settings()
    if not settings.database_url:
        return None
    if _session_factory is None:
        from greenlead.repositories.sql import (
            build_engine,
            create_all,
            make_session_factory,
        )

        _engine = build_engine(settings.database_url)
        # Production schema is owned by Alembic ("alembic upgrade head"); never
        # auto-create there. Dev/test convenience only.
        if settings.app_env != "production":
            create_all(_engine)
        _session_factory = make_session_factory(_engine)
    return _session_factory


def get_user_repository() -> UserRepository:
    """Return the configured UserRepository singleton (SQL > memory)."""
    global _user_repo_instance
    if _user_repo_instance is not None:
        return _user_repo_instance
    sf = _get_session_factory()
    if sf is not None:
        from greenlead.repositories.sql import SqlUserRepository

        _user_repo_instance = SqlUserRepository(sf)
    else:
        _user_repo_instance = InMemoryUserRepository()
    return _user_repo_instance


def get_audit_repository() -> AuditRepository:
    """Return the configured AuditRepository singleton (SQL > memory)."""
    global _audit_repo_instance
    if _audit_repo_instance is not None:
        return _audit_repo_instance
    sf = _get_session_factory()
    if sf is not None:
        from greenlead.repositories.sql import SqlAuditRepository

        _audit_repo_instance = SqlAuditRepository(sf)
    else:
        _audit_repo_instance = InMemoryAuditRepository()
    return _audit_repo_instance


def get_product_event_repository() -> ProductEventRepository:
    """Return the configured ProductEventRepository singleton (SQL > memory)."""
    global _product_event_repo_instance
    if _product_event_repo_instance is not None:
        return _product_event_repo_instance
    sf = _get_session_factory()
    if sf is not None:
        from greenlead.repositories.sql import SqlProductEventRepository

        _product_event_repo_instance = SqlProductEventRepository(sf)
    else:
        _product_event_repo_instance = InMemoryProductEventRepository()
    return _product_event_repo_instance


def get_company_repository() -> CompanyRepository:
    """Return the configured CompanyRepository singleton (SQL > Sheets > memory)."""
    global _company_repo_instance
    if _company_repo_instance is not None:
        return _company_repo_instance

    settings = get_settings()
    sf = _get_session_factory()
    if sf is not None:
        from greenlead.repositories.sql import SqlCompanyRepository

        _company_repo_instance = SqlCompanyRepository(sf)
    elif settings.google_sheet_id and settings.google_service_account_file:
        from greenlead.repositories.sheets import GoogleSheetsCompanyRepository

        _company_repo_instance = GoogleSheetsCompanyRepository(
            spreadsheet_id=settings.google_sheet_id,
            credentials_path=settings.google_service_account_file,
        )
    else:
        _company_repo_instance = InMemoryCompanyRepository()

    return _company_repo_instance


def get_contact_repository() -> ContactRepository:
    """Return the configured ContactRepository singleton (SQL > Sheets > memory)."""
    global _contact_repo_instance
    if _contact_repo_instance is not None:
        return _contact_repo_instance

    settings = get_settings()
    sf = _get_session_factory()
    if sf is not None:
        from greenlead.repositories.sql import SqlContactRepository

        _contact_repo_instance = SqlContactRepository(sf)
    elif settings.google_sheet_id and settings.google_service_account_file:
        from greenlead.repositories.sheets import GoogleSheetsContactRepository

        _contact_repo_instance = GoogleSheetsContactRepository(
            spreadsheet_id=settings.google_sheet_id,
            credentials_path=settings.google_service_account_file,
        )
    else:
        _contact_repo_instance = InMemoryContactRepository()

    return _contact_repo_instance


def get_followup_repository() -> FollowUpRepository:
    """Return the configured FollowUpRepository singleton (SQL > memory).

    No Google Sheets adapter exists for follow-ups; they use SQL when
    DATABASE_URL is set, otherwise in-memory.
    """
    global _followup_repo_instance
    if _followup_repo_instance is not None:
        return _followup_repo_instance

    sf = _get_session_factory()
    if sf is not None:
        from greenlead.repositories.sql import SqlFollowUpRepository

        _followup_repo_instance = SqlFollowUpRepository(sf)
    else:
        _followup_repo_instance = InMemoryFollowUpRepository()
    return _followup_repo_instance


def get_meeting_repository() -> MeetingRepository:
    """Return the configured MeetingRepository singleton (SQL > memory)."""
    global _meeting_repo_instance
    if _meeting_repo_instance is not None:
        return _meeting_repo_instance

    sf = _get_session_factory()
    if sf is not None:
        from greenlead.repositories.sql import SqlMeetingRepository

        _meeting_repo_instance = SqlMeetingRepository(sf)
    else:
        _meeting_repo_instance = InMemoryMeetingRepository()
    return _meeting_repo_instance


def check_db() -> tuple[bool, str]:
    """Readiness probe. Returns (ok, backend) for the configured persistence.

    For the SQL backend, opens a connection and runs SELECT 1. Never raises.
    """
    settings = get_settings()
    if not settings.database_url:
        return True, "in_memory"
    try:
        from sqlalchemy import text

        sf = _get_session_factory()
        assert sf is not None
        with sf() as s:
            s.execute(text("SELECT 1"))
        backend = "postgresql" if "postgres" in settings.database_url else "sqlite"
        return True, backend
    except Exception:  # noqa: BLE001
        return False, "error"


def reset_repository() -> None:
    """Reset singletons (for testing only)."""
    global _company_repo_instance, _contact_repo_instance
    global _followup_repo_instance, _meeting_repo_instance, _user_repo_instance
    global _audit_repo_instance, _product_event_repo_instance
    global _engine, _session_factory
    _user_repo_instance = None
    _audit_repo_instance = None
    _product_event_repo_instance = None
    _company_repo_instance = None
    _contact_repo_instance = None
    _followup_repo_instance = None
    _meeting_repo_instance = None
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
