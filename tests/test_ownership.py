"""Record-level authorization and IDOR regression tests.

Covers the core defect this milestone fixes: employees must see and touch only
their own records; managers/admins see the team; missing and forbidden records
are indistinguishable to an employee.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from greenlead.application import create_app
from greenlead.core.config import Settings
from greenlead.core.policy import AccessDenied
from greenlead.core.security import create_session_token
from greenlead.models.schemas import CompanyCreate, FollowUpCreate, MeetingCreate, User
from greenlead.repositories import (
    get_company_repository,
    get_followup_repository,
    get_meeting_repository,
    get_user_repository,
    reset_repository,
)
from greenlead.repositories.memory import (
    InMemoryCompanyRepository,
    InMemoryContactRepository,
    InMemoryFollowUpRepository,
    InMemoryMeetingRepository,
)
from greenlead.services.companies import CompanyService
from greenlead.services.contacts import ContactService
from greenlead.services.dashboard import DashboardService
from greenlead.services.followups import FollowUpService
from greenlead.services.users import UserService

EMP_A = User(id="ua", username="a", role="employee")
EMP_B = User(id="ub", username="b", role="employee")
MANAGER = User(id="um", username="mgr", role="manager")
ADMIN = User(id="uad", username="adm", role="admin")


# ── Service-level authorization ───────────────────────────────────────────────


def _company_service() -> CompanyService:
    return CompanyService(InMemoryCompanyRepository())


def test_employee_sees_only_owned_companies() -> None:
    svc = _company_service()
    svc.create_company_for(EMP_A, CompanyCreate(name_en="A-Co", domain="a.com"))
    svc.create_company_for(EMP_B, CompanyCreate(name_en="B-Co", domain="b.com"))
    a_names = [c.name_en for c in svc.list_companies_for(EMP_A)]
    b_names = [c.name_en for c in svc.list_companies_for(EMP_B)]
    assert a_names == ["A-Co"]
    assert b_names == ["B-Co"]


def test_manager_and_admin_see_all_companies() -> None:
    svc = _company_service()
    svc.create_company_for(EMP_A, CompanyCreate(name_en="A-Co", domain="a.com"))
    svc.create_company_for(EMP_B, CompanyCreate(name_en="B-Co", domain="b.com"))
    assert len(svc.list_companies_for(MANAGER)) == 2
    assert len(svc.list_companies_for(ADMIN)) == 2


def test_employee_cannot_get_others_company() -> None:
    svc = _company_service()
    c = svc.create_company_for(EMP_A, CompanyCreate(name_en="A-Co", domain="a.com"))
    with pytest.raises(AccessDenied):
        svc.get_company_for(EMP_B, c.id)
    # Owner and manager can.
    assert svc.get_company_for(EMP_A, c.id).id == c.id
    assert svc.get_company_for(MANAGER, c.id).id == c.id


def test_employee_cannot_edit_or_reassign_others_company() -> None:
    svc = _company_service()
    c = svc.create_company_for(EMP_A, CompanyCreate(name_en="A-Co", domain="a.com"))
    with pytest.raises(AccessDenied):
        svc.update_company_for(EMP_B, c.id, {"sector": "x"})
    with pytest.raises(AccessDenied):
        svc.reassign_for(EMP_A, c.id, EMP_B.id)  # employee may not reassign


def test_manager_reassign_transfers_visibility() -> None:
    repo = InMemoryCompanyRepository()
    svc = CompanyService(repo)
    c = svc.create_company_for(EMP_A, CompanyCreate(name_en="A-Co", domain="a.com"))
    assert svc.list_companies_for(EMP_B) == []
    svc.reassign_for(MANAGER, c.id, EMP_B.id)
    assert [x.id for x in svc.list_companies_for(EMP_B)] == [c.id]
    assert svc.list_companies_for(EMP_A) == []


def test_child_records_follow_company_ownership() -> None:
    comp_repo = InMemoryCompanyRepository()
    contact_repo = InMemoryContactRepository()
    fu_repo = InMemoryFollowUpRepository()
    companies = CompanyService(comp_repo)
    contacts = ContactService(contact_repo, comp_repo)
    fups = FollowUpService(fu_repo, comp_repo)

    company = companies.create_company_for(
        EMP_A, CompanyCreate(name_en="A-Co", domain="a.com")
    )
    # A creates a follow-up on their company; B must not see or fetch it.
    fu = fups.create_followup_for(
        EMP_A, FollowUpCreate(company_id=company.id, title="call")
    )
    assert fups.list_followups_for(EMP_B) == []
    with pytest.raises(AccessDenied):
        fups.get_followup_for(EMP_B, fu.id)
    # B cannot create a contact under A's company either.
    from greenlead.models.schemas import ContactCreate

    with pytest.raises(AccessDenied):
        contacts.create_contact_for(
            EMP_B, ContactCreate(company_id=company.id, name="X")
        )


def test_dashboard_counts_are_scoped_to_actor() -> None:
    comp_repo = InMemoryCompanyRepository()
    contact_repo = InMemoryContactRepository()
    meet_repo = InMemoryMeetingRepository()
    companies = CompanyService(comp_repo)
    a_co = companies.create_company_for(
        EMP_A, CompanyCreate(name_en="A", domain="a.com")
    )
    companies.create_company_for(EMP_B, CompanyCreate(name_en="B", domain="b.com"))
    MeetingServiceLocal = __import__(
        "greenlead.services.meetings", fromlist=["MeetingService"]
    ).MeetingService
    ms = MeetingServiceLocal(meet_repo, comp_repo, contact_repo)
    ms.create_meeting_for(
        EMP_A,
        MeetingCreate(
            company_id=a_co.id,
            subject="S",
            meeting_type="Phone",
            meeting_date="2026-08-01",
        ),
    )
    settings = Settings(google_sheet_id="", google_service_account_file="")
    # Pin the dashboard clock so this ownership test remains deterministic.
    # Upcoming deliberately excludes meetings on ``today``; date semantics are
    # covered separately by the meeting service tests.
    dash_a = DashboardService(
        comp_repo,
        contact_repo,
        settings,
        meeting_repo=meet_repo,
        today=date(2026, 7, 31),
        actor=EMP_A,
    )
    dash_b = DashboardService(
        comp_repo,
        contact_repo,
        settings,
        meeting_repo=meet_repo,
        today=date(2026, 7, 31),
        actor=EMP_B,
    )
    assert dash_a.get_dashboard_summary().total_companies == 1
    assert dash_b.get_dashboard_summary().total_companies == 1
    assert dash_a.get_dashboard_summary().upcoming_meetings_count == 1
    assert dash_b.get_dashboard_summary().upcoming_meetings_count == 0


# ── Route-level IDOR ──────────────────────────────────────────────────────────


def _client() -> TestClient:
    return TestClient(create_app(), follow_redirects=False)


def _session(username: str) -> dict[str, str]:
    return {"session": create_session_token(username)}


def _seed_two_employees() -> tuple[User, User]:
    svc = UserService(get_user_repository())
    from greenlead.models.schemas import UserCreate

    a = svc.create_user(
        UserCreate(username="emp_a", password="pw12345", role="employee")
    )
    b = svc.create_user(
        UserCreate(username="emp_b", password="pw12345", role="employee")
    )
    return a, b


def test_idor_employee_cannot_open_others_company_by_url() -> None:
    reset_repository()
    _seed_two_employees()
    # emp_a creates a company via the route (owned by emp_a).
    ca = _client()
    ca.cookies.update(_session("emp_a"))
    ca.post("/companies/new", data={"name_en": "A-Co", "domain": "a.com"})
    company = get_company_repository().list_companies()[0]

    # emp_b probes the id directly -> 404 (indistinguishable from non-existent).
    cb = _client()
    cb.cookies.update(_session("emp_b"))
    resp = cb.get(f"/companies/{company.id}")
    assert resp.status_code == 404
    # emp_b's own company list is empty.
    assert "A-Co" not in cb.get("/companies/").text


def test_idor_employee_cannot_open_others_followup() -> None:
    reset_repository()
    _seed_two_employees()
    ca = _client()
    ca.cookies.update(_session("emp_a"))
    ca.post("/companies/new", data={"name_en": "A-Co", "domain": "a.com"})
    company = get_company_repository().list_companies()[0]
    ca.post(
        "/followups/new",
        data={"company_id": company.id, "title": "call", "priority": "Medium"},
    )
    fu = get_followup_repository().list_followups()[0]

    cb = _client()
    cb.cookies.update(_session("emp_b"))
    assert cb.get(f"/followups/{fu.id}").status_code == 404


def test_idor_employee_cannot_open_others_meeting() -> None:
    reset_repository()
    _seed_two_employees()
    ca = _client()
    ca.cookies.update(_session("emp_a"))
    ca.post("/companies/new", data={"name_en": "A-Co", "domain": "a.com"})
    company = get_company_repository().list_companies()[0]
    ca.post(
        "/meetings/new",
        data={
            "company_id": company.id,
            "subject": "S",
            "meeting_type": "Phone",
            "meeting_date": "2026-08-01",
        },
    )
    m = get_meeting_repository().list_meetings()[0]

    cb = _client()
    cb.cookies.update(_session("emp_b"))
    assert cb.get(f"/meetings/{m.id}").status_code == 404
    assert cb.get(f"/meetings/{m.id}/ics").status_code == 404


def test_admin_sees_all_via_routes() -> None:
    reset_repository()
    _seed_two_employees()
    ca = _client()
    ca.cookies.update(_session("emp_a"))
    ca.post("/companies/new", data={"name_en": "Visible-To-Admin", "domain": "a.com"})

    admin_c = _client()
    admin_c.cookies.update(_session("admin"))
    assert "Visible-To-Admin" in admin_c.get("/companies/").text
