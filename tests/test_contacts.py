"""Tests for Contact Management (model, repository, service, and routes).

All tests run in-memory without requiring external services or Google credentials.
"""

from fastapi.testclient import TestClient

from greenlead.application import create_app
from greenlead.models.schemas import CompanyCreate, Contact, ContactCreate
from greenlead.repositories import (
    get_company_repository,
    get_contact_repository,
    reset_repository,
)
from greenlead.repositories.memory import InMemoryContactRepository
from greenlead.repositories.sheets import (
    CONTACT_HEADERS,
    _contact_to_row,
    _row_to_contact,
)
from greenlead.services.contacts import ContactService

app = create_app()
client = TestClient(app, follow_redirects=False)


def _login() -> None:
    from greenlead.core.security import create_session_token

    client.cookies.set("session", create_session_token("admin"))


# ── Model & Mapping Tests ───────────────────────────────────────────────────


def test_contact_model_fields() -> None:
    contact = Contact(
        id="c1",
        company_id="comp1",
        name="Tariq Al-Mansoor",
        title="CISO",
        email="tariq@example.sa",
        phone="+966500000000",
        relationship_level="Decision Maker",
        is_decision_maker=True,
        source_url="https://linkedin.com/in/tariq",
        notes="Key decision maker for security",
    )
    assert contact.id == "c1"
    assert contact.is_decision_maker is True
    assert contact.relationship_level == "Decision Maker"


def test_row_to_contact_valid() -> None:
    row = {
        "id": "c100",
        "company_id": "comp100",
        "name": "Sarah Ahmed",
        "title": "IT Director",
        "email": "sarah@tech.sa",
        "phone": "0512345678",
        "relationship_level": "Executive",
        "is_decision_maker": "true",
        "source_url": "https://tech.sa/about",
        "verification_status": "verified",
        "notes": "Met at Conference",
        "created_at": "2026-01-01",
        "updated_at": "2026-01-02",
    }
    contact = _row_to_contact(row)
    assert contact is not None
    assert contact.id == "c100"
    assert contact.is_decision_maker is True
    assert contact.title == "IT Director"


def test_row_to_contact_missing_required() -> None:
    assert _row_to_contact({"id": "c1", "name": ""}) is None
    assert _row_to_contact({"id": "", "name": "Sarah", "company_id": "comp1"}) is None
    assert _row_to_contact({"id": "c1", "name": "Sarah", "company_id": ""}) is None


def test_contact_to_row_roundtrip() -> None:
    repo = InMemoryContactRepository()
    created = repo.create_contact(
        ContactCreate(
            company_id="comp1",
            name="Ahmad Omar",
            title="VP Cyber",
            is_decision_maker=True,
        )
    )
    row = _contact_to_row(created)
    assert len(row) == len(CONTACT_HEADERS)
    assert row[0] == created.id
    assert row[1] == "comp1"
    assert row[2] == "Ahmad Omar"
    assert row[7] == "true"


# ── Repository Tests ─────────────────────────────────────────────────────────


def test_contact_repo_crud() -> None:
    repo = InMemoryContactRepository()

    # Create
    c1 = repo.create_contact(
        ContactCreate(company_id="comp1", name="Alice", title="CTO")
    )
    assert c1.id
    assert c1.name == "Alice"

    # List by company
    contacts = repo.list_contacts_by_company("comp1")
    assert len(contacts) == 1
    assert contacts[0].id == c1.id

    # Get
    assert repo.get_contact(c1.id) is not None
    assert repo.get_contact("nonexistent") is None

    # Update
    updated = repo.update_contact(c1.id, {"title": "Chief Technology Officer"})
    assert updated.title == "Chief Technology Officer"

    # Delete
    assert repo.delete_contact(c1.id) is True
    assert len(repo.list_contacts_by_company("comp1")) == 0
    assert repo.delete_contact(c1.id) is False


# ── Service Tests ────────────────────────────────────────────────────────────


def test_contact_service_company_validation() -> None:
    reset_repository()
    company_repo = get_company_repository()
    contact_repo = get_contact_repository()
    service = ContactService(contact_repo, company_repo)

    # Creating contact for non-existent company raises KeyError
    try:
        service.create_contact(ContactCreate(company_id="invalid-comp-id", name="John"))
        assert False, "Should have raised KeyError"
    except KeyError:
        pass

    # Create company first
    comp = company_repo.create_company(CompanyCreate(name_en="Valid Company"))
    contact = service.create_contact(
        ContactCreate(company_id=comp.id, name="John", is_decision_maker=True)
    )
    assert contact.company_id == comp.id
    reset_repository()


def test_contact_service_empty_name() -> None:
    reset_repository()
    company_repo = get_company_repository()
    contact_repo = get_contact_repository()
    service = ContactService(contact_repo, company_repo)
    comp = company_repo.create_company(CompanyCreate(name_en="Valid Company"))

    try:
        service.create_contact(ContactCreate(company_id=comp.id, name="   "))
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    reset_repository()


# ── Route Integration Tests ─────────────────────────────────────────────────


def test_contacts_routes_unauthenticated() -> None:
    reset_repository()
    resp = client.get("/companies/some-id/contacts/new")
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("location", "")


def test_contacts_create_and_render_flow() -> None:
    reset_repository()
    _login()

    # 1. Create company
    comp_repo = get_company_repository()
    company = comp_repo.create_company(
        CompanyCreate(name_en="CyberTech Ltd", domain="cybertech.sa")
    )

    # 2. Open new contact form
    form_resp = client.get(f"/companies/{company.id}/contacts/new")
    assert form_resp.status_code == 200
    assert "CyberTech Ltd" in form_resp.text

    # 3. Create contact
    create_resp = client.post(
        f"/companies/{company.id}/contacts/new",
        data={
            "name": "Faisal Al-Otaibi",
            "title": "Head of Infrastructure",
            "email": "faisal@cybertech.sa",
            "phone": "0501112233",
            "relationship_level": "Decision Maker",
            "is_decision_maker": "true",
            "notes": "Primary technical contact",
        },
    )
    assert create_resp.status_code == 303
    assert f"/companies/{company.id}" in create_resp.headers.get("location", "")

    # 4. View company detail showing the created contact
    detail_resp = client.get(f"/companies/{company.id}")
    assert detail_resp.status_code == 200
    assert "Faisal Al-Otaibi" in detail_resp.text
    assert "Head of Infrastructure" in detail_resp.text
    assert "صانع قرار" in detail_resp.text or "Decision Maker" in detail_resp.text

    # 5. Edit contact
    contact_repo = get_contact_repository()
    contacts = contact_repo.list_contacts_by_company(company.id)
    assert len(contacts) == 1
    contact_id = contacts[0].id

    edit_form_resp = client.get(f"/companies/{company.id}/contacts/{contact_id}/edit")
    assert edit_form_resp.status_code == 200
    assert "Faisal Al-Otaibi" in edit_form_resp.text

    edit_post_resp = client.post(
        f"/companies/{company.id}/contacts/{contact_id}/edit",
        data={
            "name": "Faisal Al-Otaibi (Promoted)",
            "title": "CIO",
            "email": "faisal@cybertech.sa",
            "phone": "0501112233",
            "relationship_level": "Executive",
            "is_decision_maker": "true",
            "notes": "Updated title",
        },
    )
    assert edit_post_resp.status_code == 303

    # 6. Delete contact
    delete_resp = client.post(f"/companies/{company.id}/contacts/{contact_id}/delete")
    assert delete_resp.status_code == 303

    detail_after_del = client.get(f"/companies/{company.id}")
    assert "Faisal Al-Otaibi (Promoted)" not in detail_after_del.text
    reset_repository()
