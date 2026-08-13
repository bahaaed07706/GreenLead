"""Tests for Consolidated Operational Dashboard (Service and Routes).

Covers zero-data behavior, metric aggregation, data quality alerts, storage status,
research status, bilingual rendering (Arabic & English), and error handling.
"""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from greenlead.application import create_app
from greenlead.core.config import Settings
from greenlead.models.schemas import CompanyCreate, ContactCreate
from greenlead.repositories import (
    get_company_repository,
    get_contact_repository,
    reset_repository,
)
from greenlead.repositories.memory import (
    InMemoryCompanyRepository,
    InMemoryContactRepository,
)
from greenlead.services.dashboard import DashboardService

app = create_app()
client = TestClient(app, follow_redirects=False)


def _login() -> None:
    from greenlead.core.security import create_session_token

    client.cookies.set("session", create_session_token("admin"))


# ── Service Unit Tests ────────────────────────────────────────────────────────


def test_dashboard_service_zero_data() -> None:
    comp_repo = InMemoryCompanyRepository()
    contact_repo = InMemoryContactRepository()
    settings = Settings(google_sheet_id="", google_service_account_file="")
    service = DashboardService(comp_repo, contact_repo, settings)

    summary = service.get_dashboard_summary()

    assert summary.total_companies == 0
    assert summary.total_contacts == 0
    assert summary.decision_makers_count == 0
    assert summary.verified_contacts_count == 0
    assert summary.companies_without_contacts_count == 0
    assert summary.companies_without_decision_maker_count == 0
    assert summary.contacts_missing_source_url_count == 0
    assert len(summary.work_queue) == 0
    assert summary.storage_status.state == "not_configured"
    assert summary.storage_status.backend_type == "in_memory"
    assert summary.research_status.state == "not_configured"
    assert summary.research_status.provider_type == "mock"
    assert summary.ai_status.state == "not_configured"


def test_dashboard_work_queue_generation_and_severities() -> None:
    comp_repo = InMemoryCompanyRepository()
    contact_repo = InMemoryContactRepository()
    settings = Settings(google_sheet_id="", google_service_account_file="")
    service = DashboardService(comp_repo, contact_repo, settings)

    # 1. Company with no contacts -> High severity work queue item
    cA = comp_repo.create_company(
        CompanyCreate(name_en="Alpha Corp", domain="alpha.com")
    )

    # 2. Company with contact but no decision maker -> Medium severity work queue item
    cB = comp_repo.create_company(CompanyCreate(name_en="Beta Corp", domain="beta.com"))
    contact_repo.create_contact(
        ContactCreate(
            company_id=cB.id,
            name="Bob",
            title="Engineer",
            is_decision_maker=False,
            relationship_level="Contact",
            source_url="https://beta.com/bob",
            verification_status="verified",
        )
    )

    # 3. Unverified contact missing source URL -> Low/Medium severity items
    cC = comp_repo.create_company(
        CompanyCreate(name_en="Gamma Corp", domain="gamma.com")
    )
    contact_repo.create_contact(
        ContactCreate(
            company_id=cC.id,
            name="Charlie",
            title="Manager",
            is_decision_maker=True,
            relationship_level="Decision Maker",
            source_url="",  # missing source URL -> Low severity item
            verification_status="unverified",  # unverified -> Medium severity item
        )
    )

    summary = service.get_dashboard_summary()
    wq = summary.work_queue

    assert len(wq) > 0

    # Ensure queue items are ordered by severity rank: high -> medium -> low
    severities = [item.severity for item in wq]
    assert severities[0] == "high"

    # Verify high severity item for Company A (no contacts)
    high_item = next(item for item in wq if item.record_id == cA.id)
    assert high_item.severity == "high"
    assert high_item.link_url == f"/companies/{cA.id}/contacts/new"
    assert high_item.action_label_en == "+ Add Contact"

    # Verify medium severity item for Company B (no decision maker)
    med_item = next(item for item in wq if item.record_id == cB.id)
    assert med_item.severity == "medium"
    assert med_item.link_url == f"/companies/{cB.id}"
    assert med_item.action_label_en == "Assign Decision Maker"


def test_dashboard_work_queue_clears_dynamically() -> None:
    comp_repo = InMemoryCompanyRepository()
    contact_repo = InMemoryContactRepository()
    settings = Settings(google_sheet_id="", google_service_account_file="")
    service = DashboardService(comp_repo, contact_repo, settings)

    # Initially company has no contacts
    cA = comp_repo.create_company(
        CompanyCreate(name_en="Delta Corp", domain="delta.com")
    )
    s1 = service.get_dashboard_summary()
    assert len(s1.work_queue) == 1
    assert s1.work_queue[0].issue_title_en == "Company Has No Contacts"

    # Add contact to Delta Corp
    contact = contact_repo.create_contact(
        ContactCreate(
            company_id=cA.id,
            name="Diana",
            title="VP Security",
            is_decision_maker=False,
            relationship_level="Executive",
            source_url="https://delta.com/diana",
        )
    )
    s2 = service.get_dashboard_summary()
    # "Company Has No Contacts" issue clears, replaced by "No Decision Maker Designated" & "Unverified Contact"
    assert not any(
        item.issue_title_en == "Company Has No Contacts" for item in s2.work_queue
    )
    assert any(
        item.issue_title_en == "No Decision Maker Designated" for item in s2.work_queue
    )

    # Mark Diana as Decision Maker and verified
    contact_repo.update_contact(
        contact.id, {"is_decision_maker": True, "verification_status": "verified"}
    )
    s3 = service.get_dashboard_summary()
    # All issues cleared for Delta Corp
    assert not any(
        item.record_id == cA.id or item.record_id == contact.id
        for item in s3.work_queue
    )


def test_dashboard_service_explicit_integration_states() -> None:
    comp_repo = InMemoryCompanyRepository()
    contact_repo = InMemoryContactRepository()
    settings = Settings(
        google_sheet_id="test-sheet-id",
        google_service_account_file="creds.json",
        tavily_api_key="tvly-test-key",
        ai_provider="openai",
        openai_api_key="sk-test-key",
    )

    service_unverified = DashboardService(comp_repo, contact_repo, settings)
    summary_unverified = service_unverified.get_dashboard_summary()

    assert summary_unverified.storage_status.state == "configured_unverified"
    assert summary_unverified.research_status.state == "configured_unverified"
    assert summary_unverified.ai_status.state == "configured_unverified"
    assert summary_unverified.ai_status.provider_type == "openai"

    service_verified = DashboardService(
        comp_repo,
        contact_repo,
        settings,
        sheets_verified=True,
        tavily_verified=True,
        ai_verified=True,
    )
    summary_verified = service_verified.get_dashboard_summary()

    assert summary_verified.storage_status.state == "live_verified"
    assert summary_verified.research_status.state == "live_verified"
    assert summary_verified.ai_status.state == "live_verified"


def test_ai_status_not_configured_without_key() -> None:
    comp_repo = InMemoryCompanyRepository()
    contact_repo = InMemoryContactRepository()
    # AI provider named but no key -> still not configured.
    settings = Settings(ai_provider="openai", openai_api_key="", gemini_api_key="")
    service = DashboardService(comp_repo, contact_repo, settings, ai_verified=True)
    summary = service.get_dashboard_summary()
    assert summary.ai_status.state == "not_configured"


def test_dashboard_service_metric_aggregation() -> None:
    comp_repo = InMemoryCompanyRepository()
    contact_repo = InMemoryContactRepository()
    settings = Settings(
        google_sheet_id="test-sheet-id",
        google_service_account_file="creds.json",
        tavily_api_key="tvly-test-key",
    )
    service = DashboardService(comp_repo, contact_repo, settings)

    cA = comp_repo.create_company(
        CompanyCreate(name_en="Alpha Security", sector="Cybersecurity")
    )
    contact_repo.create_contact(
        ContactCreate(
            company_id=cA.id,
            name="Alice",
            title="CISO",
            relationship_level="Decision Maker",
            is_decision_maker=True,
            source_url="https://alpha.sec/alice",
        )
    )
    contact_repo.create_contact(
        ContactCreate(
            company_id=cA.id,
            name="Bob",
            title="Engineer",
            relationship_level="Contact",
            is_decision_maker=False,
            source_url="",
        )
    )

    comp_repo.create_company(CompanyCreate(name_en="Beta Cloud", sector="Cloud"))

    summary = service.get_dashboard_summary()

    assert summary.total_companies == 2
    assert summary.total_contacts == 2
    assert summary.decision_makers_count == 1
    assert summary.companies_without_contacts_count == 1
    assert summary.companies_without_decision_maker_count == 1
    assert summary.contacts_missing_source_url_count == 1
    assert summary.sectors_breakdown.get("Cybersecurity") == 1
    assert summary.sectors_breakdown.get("Cloud") == 1


# ── Route Integration Tests ───────────────────────────────────────────────────


def test_dashboard_unauthenticated_redirect() -> None:
    reset_repository()
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("location", "")


def test_dashboard_authenticated_zero_data() -> None:
    reset_repository()
    _login()
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Operational Workspace" in resp.text or "لوحة القيادة" in resp.text
    reset_repository()


def test_dashboard_bilingual_arabic_rendering() -> None:
    reset_repository()
    _login()

    comp_repo = get_company_repository()
    contact_repo = get_contact_repository()
    cA = comp_repo.create_company(
        CompanyCreate(name_en="Saudi Cyber", name_ar="الشركة السعودية للأمن السيبراني")
    )
    contact_repo.create_contact(
        ContactCreate(
            company_id=cA.id,
            name="طارق المنصور",
            title="CISO",
            is_decision_maker=True,
        )
    )

    client.cookies.set("lang", "ar")
    resp = client.get("/")
    assert resp.status_code == 200
    assert "إجمالي الشركات" in resp.text
    assert 'dir="rtl"' in resp.text
    reset_repository()


def test_dashboard_bilingual_english_rendering() -> None:
    reset_repository()
    _login()

    client.cookies.set("lang", "en")
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Total Companies" in resp.text
    assert 'dir="ltr"' in resp.text
    reset_repository()


def test_dashboard_repository_error_resilience() -> None:
    reset_repository()
    _login()

    mock_comp_repo = MagicMock()
    mock_comp_repo.list_companies.side_effect = RuntimeError(
        "Storage connection failed"
    )
    mock_contact_repo = MagicMock()

    service = DashboardService(mock_comp_repo, mock_contact_repo)
    summary = service.get_dashboard_summary()

    assert summary.total_companies == 0
    assert summary.total_contacts == 0
    reset_repository()
