"""Phase 4 tests: Company Management routes and service.

All tests run with InMemoryCompanyRepository — no Google credentials needed.
The repository singleton is reset before each test that modifies state.
"""

from fastapi.testclient import TestClient

from greenlead.application import create_app
from greenlead.repositories import reset_repository

app = create_app()
client = TestClient(app, follow_redirects=False)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _login() -> None:
    """Establish an authenticated session on the test client."""
    from greenlead.core.security import create_session_token

    client.cookies.set("session", create_session_token("admin"))


# ── Service unit tests ────────────────────────────────────────────────────────


def test_company_service_create() -> None:
    from greenlead.models.schemas import CompanyCreate
    from greenlead.repositories.memory import InMemoryCompanyRepository
    from greenlead.services.companies import CompanyService

    repo = InMemoryCompanyRepository()
    svc = CompanyService(repo)
    company = svc.create_company(
        CompanyCreate(name_en="Alpha Corp", domain="alpha.com")
    )
    assert company.name_en == "Alpha Corp"
    assert company.domain == "alpha.com"


def test_company_service_duplicate_domain() -> None:
    from greenlead.models.schemas import CompanyCreate
    from greenlead.repositories.memory import InMemoryCompanyRepository
    from greenlead.services.companies import CompanyService, DuplicateDomainError

    repo = InMemoryCompanyRepository()
    svc = CompanyService(repo)
    svc.create_company(CompanyCreate(name_en="Alpha Corp", domain="alpha.com"))
    try:
        svc.create_company(CompanyCreate(name_en="Alpha 2", domain="https://alpha.com"))
        assert False, "Should have raised DuplicateDomainError"
    except DuplicateDomainError:
        pass


def test_company_service_list() -> None:
    from greenlead.models.schemas import CompanyCreate
    from greenlead.repositories.memory import InMemoryCompanyRepository
    from greenlead.services.companies import CompanyService

    repo = InMemoryCompanyRepository()
    svc = CompanyService(repo)
    assert svc.list_companies() == []
    svc.create_company(CompanyCreate(name_en="A"))
    svc.create_company(CompanyCreate(name_en="B"))
    assert len(svc.list_companies()) == 2


def test_company_service_search_by_name() -> None:
    from greenlead.models.schemas import CompanyCreate
    from greenlead.repositories.memory import InMemoryCompanyRepository
    from greenlead.services.companies import CompanyService

    repo = InMemoryCompanyRepository()
    svc = CompanyService(repo)
    svc.create_company(
        CompanyCreate(name_en="Saudi Cyber Systems", domain="saudicyber.sa")
    )
    svc.create_company(CompanyCreate(name_en="Alpha Cloud", domain="alphacloud.com"))

    results = svc.list_companies(q="Saudi")
    assert len(results) == 1
    assert results[0].name_en == "Saudi Cyber Systems"


def test_company_service_search_by_domain() -> None:
    from greenlead.models.schemas import CompanyCreate
    from greenlead.repositories.memory import InMemoryCompanyRepository
    from greenlead.services.companies import CompanyService

    repo = InMemoryCompanyRepository()
    svc = CompanyService(repo)
    svc.create_company(
        CompanyCreate(name_en="Saudi Cyber Systems", domain="saudicyber.sa")
    )
    svc.create_company(CompanyCreate(name_en="Alpha Cloud", domain="alphacloud.com"))

    results = svc.list_companies(q="alphacloud")
    assert len(results) == 1
    assert results[0].name_en == "Alpha Cloud"


def test_company_service_search_no_results() -> None:
    from greenlead.models.schemas import CompanyCreate
    from greenlead.repositories.memory import InMemoryCompanyRepository
    from greenlead.services.companies import CompanyService

    repo = InMemoryCompanyRepository()
    svc = CompanyService(repo)
    svc.create_company(
        CompanyCreate(name_en="Saudi Cyber Systems", domain="saudicyber.sa")
    )

    results = svc.list_companies(q="NonexistentTerm999")
    assert len(results) == 0


# ── Route integration tests ───────────────────────────────────────────────────


def test_companies_list_redirects_unauthenticated() -> None:
    reset_repository()
    resp = client.get("/companies/")
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("location", "")


def test_companies_list_authenticated() -> None:
    reset_repository()
    _login()
    resp = client.get("/companies/")
    assert resp.status_code == 200
    assert "companies" in resp.text.lower() or "شركات" in resp.text


def test_companies_search_route_name() -> None:
    reset_repository()
    _login()
    client.post(
        "/companies/new", data={"name_en": "Riyadh Cyber", "domain": "riyadhcyber.sa"}
    )
    client.post(
        "/companies/new", data={"name_en": "Jeddah Tech", "domain": "jeddahtech.sa"}
    )

    resp = client.get("/companies/?q=Riyadh")
    assert resp.status_code == 200
    assert "Riyadh Cyber" in resp.text
    assert "Jeddah Tech" not in resp.text
    assert 'value="Riyadh"' in resp.text
    reset_repository()


def test_companies_search_route_domain() -> None:
    reset_repository()
    _login()
    client.post(
        "/companies/new", data={"name_en": "Riyadh Cyber", "domain": "riyadhcyber.sa"}
    )
    client.post(
        "/companies/new", data={"name_en": "Jeddah Tech", "domain": "jeddahtech.sa"}
    )

    resp = client.get("/companies/?q=jeddahtech")
    assert resp.status_code == 200
    assert "Jeddah Tech" in resp.text
    assert "Riyadh Cyber" not in resp.text
    reset_repository()


def test_companies_search_route_no_results() -> None:
    reset_repository()
    _login()
    client.post(
        "/companies/new", data={"name_en": "Riyadh Cyber", "domain": "riyadhcyber.sa"}
    )

    resp = client.get("/companies/?q=NonexistentQuery999")
    assert resp.status_code == 200
    assert "No search results found" in resp.text or "لم يتم العثور" in resp.text
    reset_repository()


def test_companies_new_form_renders() -> None:
    reset_repository()
    _login()
    resp = client.get("/companies/new")
    assert resp.status_code == 200
    assert "name_en" in resp.text


def test_companies_create_valid() -> None:
    reset_repository()
    _login()
    resp = client.post(
        "/companies/new",
        data={
            "name_en": "Test Corp",
            "name_ar": "شركة تجريبية",
            "domain": "testcorp.com",
            "sector": "Technology",
            "city": "Riyadh",
            "description": "A test company",
        },
    )
    assert resp.status_code == 303
    assert "/companies/" in resp.headers.get("location", "")
    reset_repository()


def test_companies_create_empty_name() -> None:
    reset_repository()
    _login()
    resp = client.post(
        "/companies/new",
        data={"name_en": "   ", "domain": ""},
    )
    assert resp.status_code == 422
    reset_repository()


def test_companies_create_duplicate_domain() -> None:
    reset_repository()
    _login()
    client.post("/companies/new", data={"name_en": "First Corp", "domain": "dup.com"})
    resp = client.post(
        "/companies/new", data={"name_en": "Second Corp", "domain": "dup.com"}
    )
    assert resp.status_code == 409
    reset_repository()


def test_companies_detail_not_found() -> None:
    reset_repository()
    _login()
    resp = client.get("/companies/nonexistent-id")
    # Missing (and forbidden) both return 404 to avoid id enumeration.
    assert resp.status_code == 404


def test_companies_detail_valid() -> None:
    reset_repository()
    _login()
    create_resp = client.post(
        "/companies/new",
        data={"name_en": "Detail Corp", "domain": "detailcorp.com"},
    )
    location = create_resp.headers.get("location", "")
    assert location.startswith("/companies/")
    detail_resp = client.get(location)
    assert detail_resp.status_code == 200
    assert "Detail Corp" in detail_resp.text
    reset_repository()


def test_dashboard_shows_company_count() -> None:
    reset_repository()
    _login()
    resp = client.get("/")
    assert resp.status_code == 200
    assert "0" in resp.text
    reset_repository()
