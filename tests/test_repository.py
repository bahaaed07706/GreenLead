"""Tests for the repository abstraction layer.

These tests run entirely with InMemoryCompanyRepository and require
no Google credentials.
"""

import pytest

from greenlead.models.schemas import Company, CompanyCreate
from greenlead.repositories.base import CompanyRepository
from greenlead.repositories.memory import InMemoryCompanyRepository


def _make_repo() -> InMemoryCompanyRepository:
    return InMemoryCompanyRepository()


def _sample_create() -> CompanyCreate:
    return CompanyCreate(
        name_en="Acme Corp",
        name_ar="شركة أكمي",
        domain="https://www.acme.com/",
        sector="Technology",
        city="Riyadh",
        description="A sample company",
    )


# --- Contract tests ---


def test_repo_implements_interface() -> None:
    repo = _make_repo()
    assert isinstance(repo, CompanyRepository)


def test_list_empty() -> None:
    repo = _make_repo()
    assert repo.list_companies() == []


def test_create_and_list() -> None:
    repo = _make_repo()
    company = repo.create_company(_sample_create())
    assert isinstance(company, Company)
    assert company.name_en == "Acme Corp"
    assert company.name_ar == "شركة أكمي"
    assert company.domain == "acme.com"  # normalized
    assert company.id  # UUID assigned
    assert company.created_at  # timestamp set

    companies = repo.list_companies()
    assert len(companies) == 1
    assert companies[0].id == company.id


def test_get_company_by_id() -> None:
    repo = _make_repo()
    company = repo.create_company(_sample_create())
    result = repo.get_company(company.id)
    assert result is not None
    assert result.id == company.id


def test_get_company_not_found() -> None:
    repo = _make_repo()
    result = repo.get_company("nonexistent-id")
    assert result is None


def test_get_company_by_domain() -> None:
    repo = _make_repo()
    repo.create_company(_sample_create())
    result = repo.get_company_by_domain("https://www.acme.com")
    assert result is not None
    assert result.name_en == "Acme Corp"


def test_get_company_by_domain_normalization() -> None:
    repo = _make_repo()
    repo.create_company(_sample_create())
    # All these should find the same company
    for variant in ["acme.com", "http://acme.com/", "https://www.acme.com/"]:
        result = repo.get_company_by_domain(variant)
        assert result is not None, f"Failed for domain variant: {variant}"


def test_get_company_by_domain_empty() -> None:
    repo = _make_repo()
    result = repo.get_company_by_domain("")
    assert result is None


def test_get_company_by_domain_not_found() -> None:
    repo = _make_repo()
    result = repo.get_company_by_domain("unknown.com")
    assert result is None


def test_update_company() -> None:
    repo = _make_repo()
    company = repo.create_company(_sample_create())
    updated = repo.update_company(company.id, {"sector": "Finance"})
    assert updated.sector == "Finance"
    assert updated.updated_at != company.updated_at


def test_update_company_not_found() -> None:
    repo = _make_repo()
    try:
        repo.update_company("nonexistent", {"sector": "Finance"})
        assert False, "Should have raised KeyError"
    except KeyError:
        pass


def test_archived_companies_excluded_from_list() -> None:
    repo = _make_repo()
    company = repo.create_company(_sample_create())
    repo.update_company(company.id, {"archived_at": "2024-01-01T00:00:00"})
    assert len(repo.list_companies()) == 0


def test_multiple_companies() -> None:
    repo = _make_repo()
    repo.create_company(CompanyCreate(name_en="Company A", domain="a.com"))
    repo.create_company(CompanyCreate(name_en="Company B", domain="b.com"))
    repo.create_company(CompanyCreate(name_en="Company C", domain="c.com"))
    assert len(repo.list_companies()) == 3


# --- Data mapping tests ---


def test_company_model_fields() -> None:
    repo = _make_repo()
    company = repo.create_company(_sample_create())
    assert company.fit_score == 0.0
    assert company.confidence_score == 0.0
    assert company.verification_status == "unverified"
    assert company.archived_at is None


def test_domain_normalization_strips_protocol() -> None:
    from greenlead.repositories.memory import _normalize_domain

    assert _normalize_domain("https://example.com") == "example.com"
    assert _normalize_domain("http://example.com/") == "example.com"
    assert _normalize_domain("http://www.example.com/") == "example.com"
    assert _normalize_domain("EXAMPLE.COM") == "example.com"


# --- Sheets row mapping tests ---


def test_row_to_company_valid() -> None:
    from greenlead.repositories.sheets import _row_to_company

    row = {
        "id": "abc-123",
        "name_en": "Test Corp",
        "name_ar": "",
        "domain": "test.com",
        "sector": "",
        "city": "",
        "description": "",
        "products": "",
        "digital_footprint": "",
        "compliance_status": "",
        "fit_score": "75.5",
        "confidence_score": "80",
        "created_at": "2024-01-01",
        "updated_at": "2024-01-02",
        "archived_at": "",
        "verification_status": "verified",
    }
    company = _row_to_company(row)
    assert company is not None
    assert company.id == "abc-123"
    assert company.name_en == "Test Corp"
    assert company.fit_score == 75.5
    assert company.archived_at is None


def test_row_to_company_missing_id() -> None:
    from greenlead.repositories.sheets import _row_to_company

    row = {"id": "", "name_en": "No ID Corp"}
    assert _row_to_company(row) is None


def test_row_to_company_missing_name() -> None:
    from greenlead.repositories.sheets import _row_to_company

    row = {"id": "abc", "name_en": ""}
    assert _row_to_company(row) is None


def test_row_to_company_malformed_score() -> None:
    from greenlead.repositories.sheets import _row_to_company

    row = {
        "id": "abc",
        "name_en": "Test",
        "fit_score": "not-a-number",
    }
    # Should return None (graceful skip)
    result = _row_to_company(row)
    assert result is None


def test_company_to_row_roundtrip() -> None:
    from greenlead.repositories.sheets import COMPANY_HEADERS, _company_to_row

    repo = _make_repo()
    company = repo.create_company(_sample_create())
    row = _company_to_row(company)
    assert len(row) == len(COMPANY_HEADERS)
    assert row[0] == company.id
    assert row[1] == "Acme Corp"


# --- Factory tests ---


def test_factory_returns_in_memory_without_config() -> None:
    from greenlead.repositories import (
        get_company_repository,
        reset_repository,
    )

    reset_repository()
    repo = get_company_repository()
    assert isinstance(repo, InMemoryCompanyRepository)
    reset_repository()


def test_factory_singleton() -> None:
    from greenlead.repositories import (
        get_company_repository,
        reset_repository,
    )

    reset_repository()
    repo1 = get_company_repository()
    repo2 = get_company_repository()
    assert repo1 is repo2
    reset_repository()


def test_factory_raises_on_invalid_sheets_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import greenlead.core.config
    import greenlead.repositories
    from greenlead.repositories import (
        get_company_repository,
        reset_repository,
    )
    from greenlead.repositories.sheets import SheetsConfigError, SheetsConnectionError

    reset_repository()

    fake_settings = greenlead.core.config.Settings(
        google_sheet_id="fake-id",
        google_service_account_file="nonexistent_key.json",
    )
    monkeypatch.setattr(greenlead.repositories, "get_settings", lambda: fake_settings)

    try:
        get_company_repository()
        assert False, "Expected SheetsConfigError or SheetsConnectionError"
    except (SheetsConfigError, SheetsConnectionError) as e:
        assert isinstance(e, (SheetsConfigError, SheetsConnectionError))
    finally:
        reset_repository()
