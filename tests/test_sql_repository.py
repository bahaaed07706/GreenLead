"""Tests for the SQL persistence backend (contract behavior + restart durability).

Runs against a temporary on-disk SQLite database — the same SQLAlchemy code path
that targets PostgreSQL in production. The restart test proves data survives a
full engine teardown (the core requirement the in-memory backend cannot meet).
"""

import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from greenlead.models.schemas import (
    CompanyCreate,
    ContactCreate,
    FollowUpCreate,
    MeetingCreate,
)
from greenlead.repositories.sql import (
    SqlCompanyRepository,
    SqlContactRepository,
    SqlFollowUpRepository,
    SqlMeetingRepository,
    build_engine,
    create_all,
    make_session_factory,
)

_TEST_ENGINES: list[Engine] = []


@pytest.fixture(autouse=True)
def dispose_test_engines() -> Generator[None, None, None]:
    """Close every per-test SQLAlchemy pool, including failure paths."""
    yield
    for engine in _TEST_ENGINES:
        engine.dispose()
    _TEST_ENGINES.clear()


@pytest.fixture
def db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'greenlead_test.db'}"


def _factory(db_url: str):
    engine = build_engine(db_url)
    _TEST_ENGINES.append(engine)
    create_all(engine)
    return make_session_factory(engine), engine


def test_company_crud_and_search(db_url: str) -> None:
    sf, _ = _factory(db_url)
    repo = SqlCompanyRepository(sf)
    c = repo.create_company(
        CompanyCreate(name_en="Acme Corp", domain="https://acme.com/")
    )
    assert c.id and c.domain == "acme.com"  # normalized
    assert repo.get_company(c.id) is not None
    assert repo.get_company_by_domain("ACME.com").id == c.id
    assert len(repo.list_companies(q="acme")) == 1
    assert repo.list_companies(q="zzz") == []
    updated = repo.update_company(c.id, {"sector": "Cybersecurity"})
    assert updated.sector == "Cybersecurity"


def test_company_archive_excluded_from_list(db_url: str) -> None:
    sf, _ = _factory(db_url)
    repo = SqlCompanyRepository(sf)
    c = repo.create_company(CompanyCreate(name_en="Gone", domain="gone.com"))
    repo.update_company(c.id, {"archived_at": "2026-07-28T00:00:00Z"})
    assert repo.list_companies() == []


def test_contact_crud(db_url: str) -> None:
    sf, _ = _factory(db_url)
    companies = SqlCompanyRepository(sf)
    contacts = SqlContactRepository(sf)
    company = companies.create_company(CompanyCreate(name_en="Acme", domain="acme.com"))
    ct = contacts.create_contact(
        ContactCreate(company_id=company.id, name="Alice", is_decision_maker=True)
    )
    assert ct.is_decision_maker is True
    assert len(contacts.list_contacts_by_company(company.id)) == 1
    contacts.update_contact(ct.id, {"verification_status": "verified"})
    assert contacts.get_contact(ct.id).verification_status == "verified"
    assert contacts.delete_contact(ct.id) is True
    assert contacts.delete_contact(ct.id) is False


def test_followup_and_meeting_crud(db_url: str) -> None:
    sf, _ = _factory(db_url)
    companies = SqlCompanyRepository(sf)
    fups = SqlFollowUpRepository(sf)
    meets = SqlMeetingRepository(sf)
    company = companies.create_company(CompanyCreate(name_en="Acme", domain="acme.com"))

    f = fups.create_followup(
        FollowUpCreate(company_id=company.id, title="Call", due_date="2026-08-01")
    )
    assert fups.get_followup(f.id).title == "Call"
    fups.update_followup(f.id, {"status": "Completed"})
    assert fups.get_followup(f.id).status == "Completed"
    assert len(fups.list_followups(company.id)) == 1

    m = meets.create_meeting(
        MeetingCreate(
            company_id=company.id,
            subject="Kickoff",
            meeting_type="Online",
            meeting_url="https://x",
        )
    )
    assert meets.get_meeting(m.id).subject == "Kickoff"
    meets.update_meeting(m.id, {"status": "Completed", "outcome": "ok"})
    assert meets.get_meeting(m.id).outcome == "ok"
    assert meets.delete_meeting(m.id) is True


def test_update_missing_raises(db_url: str) -> None:
    sf, _ = _factory(db_url)
    repo = SqlCompanyRepository(sf)
    with pytest.raises(KeyError):
        repo.update_company("does-not-exist", {"sector": "X"})


def test_data_survives_engine_restart(db_url: str) -> None:
    """Write with one engine, dispose it, reopen a fresh engine on the same file."""
    # First "process": create data.
    sf1, engine1 = _factory(db_url)
    company = SqlCompanyRepository(sf1).create_company(
        CompanyCreate(name_en="Persistent Co", domain="persist.com")
    )
    SqlFollowUpRepository(sf1).create_followup(
        FollowUpCreate(company_id=company.id, title="Survives restart")
    )
    engine1.dispose()  # simulate application shutdown

    # Second "process": brand-new engine + session factory on the same DB file.
    sf2, _ = _factory(db_url)
    companies = SqlCompanyRepository(sf2).list_companies()
    followups = SqlFollowUpRepository(sf2).list_followups()
    assert [c.name_en for c in companies] == ["Persistent Co"]
    assert [f.title for f in followups] == ["Survives restart"]


def test_check_db_ready_with_sqlite(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import greenlead.repositories as repo_pkg
    from greenlead.core.config import Settings

    monkeypatch.setattr(repo_pkg, "get_settings", lambda: Settings(database_url=db_url))
    repo_pkg.reset_repository()
    ok, backend = repo_pkg.check_db()
    assert ok is True and backend == "sqlite"
    repo_pkg.reset_repository()


def test_unique_ids_across_entities(db_url: str) -> None:
    sf, _ = _factory(db_url)
    companies = SqlCompanyRepository(sf)
    ids = {
        companies.create_company(CompanyCreate(name_en=f"C{i}", domain=f"c{i}.com")).id
        for i in range(5)
    }
    assert len(ids) == 5
    assert all(uuid.UUID(i) for i in ids)  # valid UUIDs
