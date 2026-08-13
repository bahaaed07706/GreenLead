"""Tests for the Meeting module (service, validation, derivations, ics, routes)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from greenlead.application import create_app
from greenlead.core.config import Settings
from greenlead.core.security import create_session_token
from greenlead.models.schemas import CompanyCreate, ContactCreate, MeetingCreate
from greenlead.repositories import (
    get_company_repository,
    get_meeting_repository,
    reset_repository,
)
from greenlead.repositories.memory import (
    InMemoryCompanyRepository,
    InMemoryContactRepository,
    InMemoryMeetingRepository,
)
from greenlead.services.dashboard import DashboardService
from greenlead.services.meetings import MeetingService

TODAY = date(2026, 7, 28)


def _make() -> tuple[
    MeetingService, InMemoryCompanyRepository, InMemoryContactRepository, str
]:
    comp_repo = InMemoryCompanyRepository()
    contact_repo = InMemoryContactRepository()
    meet_repo = InMemoryMeetingRepository()
    service = MeetingService(meet_repo, comp_repo, contact_repo)
    company = comp_repo.create_company(
        CompanyCreate(name_en="Acme Corp", domain="acme.com")
    )
    return service, comp_repo, contact_repo, company.id


def _online(company_id: str, **kw: object) -> MeetingCreate:
    base: dict = {
        "company_id": company_id,
        "subject": "Discovery call",
        "meeting_type": "Online",
        "meeting_url": "https://meet.example.com/abc",
        "meeting_date": "2026-08-01",
        "start_time": "10:00",
        "end_time": "10:30",
    }
    base.update(kw)
    return MeetingCreate(**base)


# ── Validation ────────────────────────────────────────────────────────────────


def test_create_online_meeting_success() -> None:
    service, _, _, cid = _make()
    m = service.create_meeting(_online(cid))
    assert m.id and m.status == "Scheduled"


def test_online_requires_url() -> None:
    service, _, _, cid = _make()
    with pytest.raises(ValueError):
        service.create_meeting(_online(cid, meeting_url=""))


def test_in_person_requires_location() -> None:
    service, _, _, cid = _make()
    with pytest.raises(ValueError):
        service.create_meeting(
            _online(cid, meeting_type="In Person", meeting_url="", location="")
        )


def test_end_must_be_after_start() -> None:
    service, _, _, cid = _make()
    with pytest.raises(ValueError):
        service.create_meeting(_online(cid, start_time="11:00", end_time="10:00"))


def test_invalid_time_rejected() -> None:
    service, _, _, cid = _make()
    with pytest.raises(ValueError):
        service.create_meeting(_online(cid, start_time="25:99", end_time=""))


def test_unknown_company_rejected() -> None:
    service, _, _, _ = _make()
    with pytest.raises(KeyError):
        service.create_meeting(_online("nope"))


def test_contact_must_belong_to_company() -> None:
    service, comp_repo, contact_repo, cid = _make()
    other = comp_repo.create_company(CompanyCreate(name_en="Other", domain="other.com"))
    contact = contact_repo.create_contact(
        ContactCreate(company_id=other.id, name="Bob")
    )
    with pytest.raises(ValueError):
        service.create_meeting(_online(cid, contact_id=contact.id))


def test_contact_belonging_to_company_ok() -> None:
    service, _, contact_repo, cid = _make()
    contact = contact_repo.create_contact(ContactCreate(company_id=cid, name="Alice"))
    m = service.create_meeting(_online(cid, contact_id=contact.id))
    assert m.contact_id == contact.id


# ── Lifecycle ─────────────────────────────────────────────────────────────────


def test_complete_and_cancel() -> None:
    service, _, _, cid = _make()
    m = service.create_meeting(_online(cid))
    done = service.complete_meeting(m.id, outcome="Good", followup_action="Send quote")
    assert done.status == "Completed" and done.outcome == "Good"
    m2 = service.create_meeting(_online(cid))
    assert service.cancel_meeting(m2.id).status == "Cancelled"


def test_invalid_status_update_rejected() -> None:
    service, _, _, cid = _make()
    m = service.create_meeting(_online(cid))
    with pytest.raises(ValueError):
        service.update_meeting(m.id, {"status": "Bogus"})


# ── Derivations ───────────────────────────────────────────────────────────────


def test_today_upcoming_missing_outcome_partition() -> None:
    service, _, _, cid = _make()
    today = service.create_meeting(_online(cid, meeting_date="2026-07-28"))
    upcoming = service.create_meeting(_online(cid, meeting_date="2026-08-10"))
    past = service.create_meeting(_online(cid, meeting_date="2026-07-01"))  # no outcome

    assert [m.id for m in service.today(TODAY)] == [today.id]
    assert [m.id for m in service.upcoming(TODAY)] == [upcoming.id]
    assert [m.id for m in service.missing_outcome(TODAY)] == [past.id]
    # Next meeting is today's (earliest by date then start time).
    assert service.next_meeting(TODAY).id == today.id


def test_completed_past_meeting_not_missing_outcome() -> None:
    service, _, _, cid = _make()
    m = service.create_meeting(_online(cid, meeting_date="2026-07-01"))
    service.complete_meeting(m.id, outcome="done")
    assert service.missing_outcome(TODAY) == []


# ── ICS export ────────────────────────────────────────────────────────────────


def test_ics_export_contains_event() -> None:
    service, _, _, cid = _make()
    m = service.create_meeting(
        _online(cid, meeting_date="2026-08-01", start_time="10:00")
    )
    ics = service.to_ics(m)
    assert "BEGIN:VCALENDAR" in ics
    assert "BEGIN:VEVENT" in ics
    assert "SUMMARY:Discovery call" in ics
    assert "DTSTART:20260801T100000" in ics
    assert ics.endswith("\r\n")


# ── Dashboard integration ─────────────────────────────────────────────────────


def test_dashboard_includes_meetings() -> None:
    comp_repo = InMemoryCompanyRepository()
    contact_repo = InMemoryContactRepository()
    meet_repo = InMemoryMeetingRepository()
    company = comp_repo.create_company(CompanyCreate(name_en="Acme", domain="acme.com"))
    svc = MeetingService(meet_repo, comp_repo, contact_repo)
    svc.create_meeting(_online(company.id, meeting_date="2026-07-28"))
    svc.create_meeting(
        _online(company.id, meeting_date="2026-07-01")
    )  # missing outcome

    settings = Settings(google_sheet_id="", google_service_account_file="")
    dash = DashboardService(
        comp_repo, contact_repo, settings, meeting_repo=meet_repo, today=TODAY
    )
    summary = dash.get_dashboard_summary()
    assert summary.meetings_today_count == 1
    assert summary.meetings_missing_outcome_count == 1
    assert summary.next_meeting is not None
    assert any(item.record_type == "Meeting" for item in summary.work_queue)


# ── Routes ────────────────────────────────────────────────────────────────────


def _client() -> TestClient:
    reset_repository()
    app = create_app()
    client = TestClient(app, follow_redirects=False)
    client.cookies.set("session", create_session_token("admin"))
    return client


def test_meeting_route_requires_auth() -> None:
    reset_repository()
    anon = TestClient(create_app(), follow_redirects=False)
    assert anon.get("/meetings/").status_code == 302


def test_meeting_create_and_ics_via_routes() -> None:
    client = _client()
    company = get_company_repository().create_company(
        CompanyCreate(name_en="Route Co", domain="route.co")
    )
    assert client.get("/meetings/").status_code == 200
    assert client.get("/meetings/new").status_code == 200

    created = client.post(
        "/meetings/new",
        data={
            "company_id": company.id,
            "subject": "Kickoff",
            "meeting_type": "Online",
            "meeting_url": "https://meet.example.com/x",
            "meeting_date": "2026-08-05",
            "start_time": "09:00",
            "end_time": "09:45",
        },
    )
    assert created.status_code == 303
    meetings = get_meeting_repository().list_meetings()
    assert len(meetings) == 1
    mid = meetings[0].id

    ics = client.get(f"/meetings/{mid}/ics")
    assert ics.status_code == 200
    assert "text/calendar" in ics.headers["content-type"]
    assert "BEGIN:VCALENDAR" in ics.text


def test_meeting_online_without_url_returns_422() -> None:
    client = _client()
    company = get_company_repository().create_company(
        CompanyCreate(name_en="X", domain="x.co")
    )
    resp = client.post(
        "/meetings/new",
        data={"company_id": company.id, "subject": "S", "meeting_type": "Online"},
    )
    assert resp.status_code == 422


def test_meeting_complete_flow_via_routes() -> None:
    client = _client()
    company = get_company_repository().create_company(
        CompanyCreate(name_en="Y", domain="y.co")
    )
    client.post(
        "/meetings/new",
        data={
            "company_id": company.id,
            "subject": "Review",
            "meeting_type": "Phone",
            "meeting_date": "2026-08-01",
        },
    )
    mid = get_meeting_repository().list_meetings()[0].id
    done = client.post(f"/meetings/{mid}/complete", data={"outcome": "Signed"})
    assert done.status_code == 303
    assert get_meeting_repository().get_meeting(mid).status == "Completed"
