"""Tests for the Follow-up module (service, date derivations, dashboard wiring).

Covers creation validation, lifecycle (complete/cancel/delete), the deterministic
overdue / due-today / upcoming derivations with an injected reference date, and
integration into the DashboardService Today view and work queue.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from greenlead.application import create_app
from greenlead.core.config import Settings
from greenlead.core.security import create_session_token
from greenlead.models.schemas import CompanyCreate, FollowUpCreate
from greenlead.repositories import (
    get_company_repository,
    get_followup_repository,
    reset_repository,
)
from greenlead.repositories.memory import (
    InMemoryCompanyRepository,
    InMemoryContactRepository,
    InMemoryFollowUpRepository,
)
from greenlead.services.dashboard import DashboardService
from greenlead.services.followups import FollowUpService

TODAY = date(2026, 7, 28)


def _make_service() -> tuple[FollowUpService, InMemoryCompanyRepository, str]:
    comp_repo = InMemoryCompanyRepository()
    fu_repo = InMemoryFollowUpRepository()
    service = FollowUpService(fu_repo, comp_repo)
    company = comp_repo.create_company(
        CompanyCreate(name_en="Acme Corp", domain="acme.com")
    )
    return service, comp_repo, company.id


# ── Creation & validation ─────────────────────────────────────────────────────


def test_create_followup_success() -> None:
    service, _, company_id = _make_service()
    fu = service.create_followup(
        FollowUpCreate(
            company_id=company_id,
            title="Send SOC proposal",
            due_date="2026-08-01",
            priority="High",
        )
    )
    assert fu.id
    assert fu.status == "Pending"
    assert fu.priority == "High"
    assert fu.created_at


def test_create_followup_unknown_company_raises() -> None:
    service, _, _ = _make_service()
    with pytest.raises(KeyError):
        service.create_followup(FollowUpCreate(company_id="does-not-exist", title="X"))


def test_create_followup_blank_title_raises() -> None:
    service, _, company_id = _make_service()
    with pytest.raises(ValueError):
        service.create_followup(FollowUpCreate(company_id=company_id, title="   "))


def test_create_followup_invalid_priority_raises() -> None:
    service, _, company_id = _make_service()
    with pytest.raises(ValueError):
        service.create_followup(
            FollowUpCreate(company_id=company_id, title="X", priority="URGENT")
        )


def test_create_followup_invalid_due_date_raises() -> None:
    service, _, company_id = _make_service()
    with pytest.raises(ValueError):
        service.create_followup(
            FollowUpCreate(company_id=company_id, title="X", due_date="31-12-2026")
        )


# ── Lifecycle ─────────────────────────────────────────────────────────────────


def test_complete_followup_stamps_completion() -> None:
    service, _, company_id = _make_service()
    fu = service.create_followup(
        FollowUpCreate(company_id=company_id, title="Call CISO", due_date="2026-07-20")
    )
    done = service.complete_followup(fu.id, outcome="Reached, positive")
    assert done.status == "Completed"
    assert done.outcome == "Reached, positive"
    assert done.completed_at is not None
    # A completed follow-up is no longer overdue.
    assert service.overdue(TODAY) == []


def test_cancel_and_delete_followup() -> None:
    service, _, company_id = _make_service()
    fu = service.create_followup(FollowUpCreate(company_id=company_id, title="X"))
    assert service.cancel_followup(fu.id).status == "Cancelled"
    assert service.delete_followup(fu.id) is True
    assert service.delete_followup(fu.id) is False


def test_update_invalid_status_raises() -> None:
    service, _, company_id = _make_service()
    fu = service.create_followup(FollowUpCreate(company_id=company_id, title="X"))
    with pytest.raises(ValueError):
        service.update_followup(fu.id, {"status": "Bogus"})


# ── Date derivations (injected today) ─────────────────────────────────────────


def test_overdue_due_today_upcoming_partition() -> None:
    service, _, company_id = _make_service()
    past = service.create_followup(
        FollowUpCreate(company_id=company_id, title="past", due_date="2026-07-01")
    )
    today = service.create_followup(
        FollowUpCreate(company_id=company_id, title="today", due_date="2026-07-28")
    )
    future = service.create_followup(
        FollowUpCreate(company_id=company_id, title="future", due_date="2026-08-15")
    )
    # No due date -> excluded from all three buckets.
    service.create_followup(FollowUpCreate(company_id=company_id, title="someday"))

    assert [f.id for f in service.overdue(TODAY)] == [past.id]
    assert [f.id for f in service.due_today(TODAY)] == [today.id]
    assert [f.id for f in service.upcoming(TODAY)] == [future.id]


def test_completed_followup_excluded_from_overdue() -> None:
    service, _, company_id = _make_service()
    fu = service.create_followup(
        FollowUpCreate(company_id=company_id, title="past", due_date="2026-07-01")
    )
    assert len(service.overdue(TODAY)) == 1
    service.complete_followup(fu.id)
    assert service.overdue(TODAY) == []


def test_list_followups_sorted_by_due_date() -> None:
    service, _, company_id = _make_service()
    service.create_followup(
        FollowUpCreate(company_id=company_id, title="b", due_date="2026-08-10")
    )
    service.create_followup(
        FollowUpCreate(company_id=company_id, title="a", due_date="2026-07-05")
    )
    titles = [f.title for f in service.list_followups()]
    assert titles == ["a", "b"]


# ── Dashboard integration ─────────────────────────────────────────────────────


def test_dashboard_includes_followup_today_view_and_work_queue() -> None:
    comp_repo = InMemoryCompanyRepository()
    contact_repo = InMemoryContactRepository()
    fu_repo = InMemoryFollowUpRepository()
    company = comp_repo.create_company(
        CompanyCreate(name_en="Acme Corp", domain="acme.com")
    )
    fu_service = FollowUpService(fu_repo, comp_repo)
    fu_service.create_followup(
        FollowUpCreate(company_id=company.id, title="overdue", due_date="2026-07-01")
    )
    fu_service.create_followup(
        FollowUpCreate(company_id=company.id, title="today", due_date="2026-07-28")
    )

    settings = Settings(google_sheet_id="", google_service_account_file="")
    service = DashboardService(
        comp_repo,
        contact_repo,
        settings,
        followup_repo=fu_repo,
        today=TODAY,
    )
    summary = service.get_dashboard_summary()

    assert summary.overdue_followups_count == 1
    assert summary.followups_due_today_count == 1
    assert any(
        item.record_type == "FollowUp" and item.severity == "high"
        for item in summary.work_queue
    )


def test_dashboard_without_followup_repo_is_backward_compatible() -> None:
    comp_repo = InMemoryCompanyRepository()
    contact_repo = InMemoryContactRepository()
    settings = Settings(google_sheet_id="", google_service_account_file="")
    service = DashboardService(comp_repo, contact_repo, settings)
    summary = service.get_dashboard_summary()
    assert summary.overdue_followups_count == 0
    assert summary.today_followups == []


# ── Route / template integration ──────────────────────────────────────────────


def _client() -> TestClient:
    reset_repository()
    app = create_app()
    client = TestClient(app, follow_redirects=False)
    client.cookies.set("session", create_session_token("admin"))
    return client


def test_followups_route_requires_auth() -> None:
    reset_repository()
    anon = TestClient(create_app(), follow_redirects=False)
    resp = anon.get("/followups/")
    assert resp.status_code == 302
    assert resp.headers["location"] == "/login"


def test_followup_create_and_complete_flow_via_routes() -> None:
    client = _client()
    company = get_company_repository().create_company(
        CompanyCreate(name_en="Route Co", domain="route.co")
    )

    # Empty list renders.
    assert client.get("/followups/").status_code == 200
    # New form renders and lists the company.
    form = client.get("/followups/new")
    assert form.status_code == 200
    assert "Route Co" in form.text

    # Create.
    created = client.post(
        "/followups/new",
        data={
            "company_id": company.id,
            "title": "Send proposal",
            "due_date": "2026-08-01",
            "priority": "High",
        },
    )
    assert created.status_code == 303

    items = get_followup_repository().list_followups()
    assert len(items) == 1
    fu_id = items[0].id

    # List now shows it.
    listing = client.get("/followups/")
    assert "Send proposal" in listing.text

    # Complete it.
    done = client.post(f"/followups/{fu_id}/complete", data={"outcome": "Sent"})
    assert done.status_code == 303
    assert get_followup_repository().get_followup(fu_id).status == "Completed"


def test_followup_create_invalid_company_returns_422() -> None:
    client = _client()
    resp = client.post(
        "/followups/new",
        data={"company_id": "nope", "title": "X", "priority": "Medium"},
    )
    assert resp.status_code == 422
