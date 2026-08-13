"""Google Sheets repository adapter.

This module isolates all Google Sheets API interaction behind the
repository interfaces. No gspread types leak outside this module.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from greenlead.models.schemas import Company, CompanyCreate, Contact, ContactCreate
from greenlead.repositories.base import CompanyRepository, ContactRepository

logger = logging.getLogger(__name__)

# Expected header row in the Companies tab (order matters for append_row)
COMPANY_HEADERS = [
    "id",
    "name_en",
    "name_ar",
    "domain",
    "sector",
    "city",
    "description",
    "products",
    "digital_footprint",
    "compliance_status",
    "fit_score",
    "confidence_score",
    "created_at",
    "updated_at",
    "archived_at",
    "verification_status",
]

# Expected header row in the Contacts tab
CONTACT_HEADERS = [
    "id",
    "company_id",
    "name",
    "title",
    "email",
    "phone",
    "relationship_level",
    "is_decision_maker",
    "source_url",
    "verification_status",
    "notes",
    "created_at",
    "updated_at",
]


class SheetsConfigError(Exception):
    """Raised when Google Sheets configuration is missing or invalid."""


class SheetsConnectionError(Exception):
    """Raised when the adapter cannot connect to Google Sheets."""


class SheetsDataError(Exception):
    """Raised when sheet data is malformed (missing headers, bad rows)."""


def _normalize_domain(domain: str) -> str:
    d = domain.lower().strip()
    for prefix in ("https://", "http://"):
        d = d.removeprefix(prefix)
    d = d.removeprefix("www.")
    return d.rstrip("/")


def _row_to_company(row: dict[str, str]) -> Company | None:
    """Convert a gspread row dict to a Company model, or None if invalid."""
    if not row.get("id") or not row.get("name_en"):
        return None
    try:
        return Company(
            id=str(row.get("id", "")),
            name_en=str(row.get("name_en", "")),
            name_ar=str(row.get("name_ar", "")),
            domain=str(row.get("domain", "")),
            sector=str(row.get("sector", "")),
            city=str(row.get("city", "")),
            description=str(row.get("description", "")),
            products=str(row.get("products", "")),
            digital_footprint=str(row.get("digital_footprint", "")),
            compliance_status=str(row.get("compliance_status", "")),
            fit_score=float(row.get("fit_score", 0) or 0),
            confidence_score=float(row.get("confidence_score", 0) or 0),
            created_at=str(row.get("created_at", "")),
            updated_at=str(row.get("updated_at", "")),
            archived_at=str(row.get("archived_at", "")) or None,
            verification_status=str(
                row.get("verification_status", "unverified") or "unverified"
            ),
        )
    except (ValueError, TypeError) as e:
        logger.warning("Skipping malformed company row: %s", e)
        return None


def _company_to_row(company: Company) -> list[str]:
    """Convert a Company model to a list of values matching COMPANY_HEADERS."""
    return [
        company.id,
        company.name_en,
        company.name_ar,
        company.domain,
        company.sector,
        company.city,
        company.description,
        company.products,
        company.digital_footprint,
        company.compliance_status,
        str(company.fit_score),
        str(company.confidence_score),
        company.created_at,
        company.updated_at,
        company.archived_at or "",
        company.verification_status,
    ]


def _row_to_contact(row: dict[str, str]) -> Contact | None:
    """Convert a gspread row dict to a Contact model, or None if invalid."""
    if not row.get("id") or not row.get("name") or not row.get("company_id"):
        return None
    try:
        is_dm_val = str(row.get("is_decision_maker", "false")).lower() in (
            "true",
            "1",
            "yes",
        )
        return Contact(
            id=str(row.get("id", "")),
            company_id=str(row.get("company_id", "")),
            name=str(row.get("name", "")),
            title=str(row.get("title", "")),
            email=str(row.get("email", "")),
            phone=str(row.get("phone", "")),
            relationship_level=str(
                row.get("relationship_level", "Contact") or "Contact"
            ),
            is_decision_maker=is_dm_val,
            source_url=str(row.get("source_url", "")),
            verification_status=str(
                row.get("verification_status", "unverified") or "unverified"
            ),
            notes=str(row.get("notes", "")),
            created_at=str(row.get("created_at", "")),
            updated_at=str(row.get("updated_at", "")),
        )
    except (ValueError, TypeError) as e:
        logger.warning("Skipping malformed contact row: %s", e)
        return None


def _contact_to_row(contact: Contact) -> list[str]:
    """Convert a Contact model to a list of values matching CONTACT_HEADERS."""
    return [
        contact.id,
        contact.company_id,
        contact.name,
        contact.title,
        contact.email,
        contact.phone,
        contact.relationship_level,
        "true" if contact.is_decision_maker else "false",
        contact.source_url,
        contact.verification_status,
        contact.notes,
        contact.created_at,
        contact.updated_at,
    ]


class GoogleSheetsCompanyRepository(CompanyRepository):
    """Google Sheets adapter implementing CompanyRepository."""

    def __init__(self, spreadsheet_id: str, credentials_path: str) -> None:
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError as e:
            raise SheetsConfigError(
                "gspread and google-auth must be installed for Google Sheets support. "
                "Install with: pip install gspread google-auth"
            ) from e

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        try:
            creds = Credentials.from_service_account_file(
                credentials_path, scopes=scopes
            )
            client = gspread.authorize(creds)
            self._spreadsheet = client.open_by_key(spreadsheet_id)
        except FileNotFoundError as e:
            raise SheetsConfigError(
                f"Service account file not found: {credentials_path}"
            ) from e
        except Exception as e:
            raise SheetsConnectionError(
                f"Failed to connect to Google Sheets: {e}"
            ) from e

    def _get_worksheet(self, tab_name: str = "Companies") -> Any:
        import gspread

        try:
            return self._spreadsheet.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound as e:
            raise SheetsDataError(f"Tab '{tab_name}' not found in spreadsheet") from e

    def _validate_headers(self, worksheet: Any) -> None:
        headers = worksheet.row_values(1)
        missing = set(COMPANY_HEADERS) - set(headers)
        if missing:
            raise SheetsDataError(
                f"Missing required headers in Companies tab: {missing}"
            )

    def list_companies(self, q: str | None = None) -> list[Company]:
        ws = self._get_worksheet()
        self._validate_headers(ws)
        rows = ws.get_all_records()
        companies = []
        for row in rows:
            company = _row_to_company(row)
            if company and company.archived_at is None:
                companies.append(company)
        if q and q.strip():
            query = q.strip().lower()
            companies = [
                c
                for c in companies
                if query in c.name_en.lower()
                or query in c.name_ar.lower()
                or query in c.domain.lower()
            ]
        return companies

    def get_company(self, company_id: str) -> Company | None:
        ws = self._get_worksheet()
        self._validate_headers(ws)
        rows = ws.get_all_records()
        for row in rows:
            if str(row.get("id", "")) == company_id:
                return _row_to_company(row)
        return None

    def get_company_by_domain(self, domain: str) -> Company | None:
        normalized = _normalize_domain(domain)
        if not normalized:
            return None
        ws = self._get_worksheet()
        self._validate_headers(ws)
        rows = ws.get_all_records()
        for row in rows:
            if _normalize_domain(str(row.get("domain", ""))) == normalized:
                return _row_to_company(row)
        return None

    def create_company(self, data: CompanyCreate) -> Company:
        ws = self._get_worksheet()
        self._validate_headers(ws)

        if data.domain:
            existing = self.get_company_by_domain(data.domain)
            if existing:
                raise ValueError(
                    f"A company with domain '{data.domain}' already exists"
                )

        now = datetime.now(UTC).isoformat()
        company = Company(
            id=str(uuid.uuid4()),
            name_en=data.name_en,
            name_ar=data.name_ar,
            domain=_normalize_domain(data.domain),
            sector=data.sector,
            city=data.city,
            description=data.description,
            created_at=now,
            updated_at=now,
        )
        ws.append_row(_company_to_row(company))
        logger.info("Created company: %s", company.name_en)
        return company

    def update_company(self, company_id: str, data: dict[str, str]) -> Company:
        ws = self._get_worksheet()
        self._validate_headers(ws)
        all_values = ws.get_all_values()
        headers = all_values[0]

        for row_idx, row in enumerate(all_values[1:], start=2):
            row_dict = dict(zip(headers, row))
            if row_dict.get("id") == company_id:
                row_dict.update(data)
                row_dict["updated_at"] = datetime.now(UTC).isoformat()
                updated_row = [row_dict.get(h, "") for h in headers]
                ws.update(
                    f"A{row_idx}:{chr(64 + len(headers))}{row_idx}", [updated_row]
                )
                company = _row_to_company(row_dict)
                if company is None:
                    raise ValueError("Update produced invalid company data")
                return company

        raise KeyError(f"Company not found: {company_id}")


class GoogleSheetsContactRepository(ContactRepository):
    """Google Sheets adapter implementing ContactRepository."""

    def __init__(self, spreadsheet_id: str, credentials_path: str) -> None:
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError as e:
            raise SheetsConfigError(
                "gspread and google-auth must be installed for Google Sheets support. "
                "Install with: pip install gspread google-auth"
            ) from e

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        try:
            creds = Credentials.from_service_account_file(
                credentials_path, scopes=scopes
            )
            client = gspread.authorize(creds)
            self._spreadsheet = client.open_by_key(spreadsheet_id)
        except FileNotFoundError as e:
            raise SheetsConfigError(
                f"Service account file not found: {credentials_path}"
            ) from e
        except Exception as e:
            raise SheetsConnectionError(
                f"Failed to connect to Google Sheets: {e}"
            ) from e

    def _get_worksheet(self, tab_name: str = "Contacts") -> Any:
        import gspread

        try:
            return self._spreadsheet.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound as e:
            raise SheetsDataError(f"Tab '{tab_name}' not found in spreadsheet") from e

    def _validate_headers(self, worksheet: Any) -> None:
        headers = worksheet.row_values(1)
        missing = set(CONTACT_HEADERS) - set(headers)
        if missing:
            raise SheetsDataError(
                f"Missing required headers in Contacts tab: {missing}"
            )

    def list_contacts_by_company(self, company_id: str) -> list[Contact]:
        ws = self._get_worksheet()
        self._validate_headers(ws)
        rows = ws.get_all_records()
        contacts = []
        for row in rows:
            if str(row.get("company_id", "")) == company_id:
                contact = _row_to_contact(row)
                if contact:
                    contacts.append(contact)
        return contacts

    def get_contact(self, contact_id: str) -> Contact | None:
        ws = self._get_worksheet()
        self._validate_headers(ws)
        rows = ws.get_all_records()
        for row in rows:
            if str(row.get("id", "")) == contact_id:
                return _row_to_contact(row)
        return None

    def create_contact(self, data: ContactCreate) -> Contact:
        ws = self._get_worksheet()
        self._validate_headers(ws)
        now = datetime.now(UTC).isoformat()
        contact = Contact(
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
            created_at=now,
            updated_at=now,
        )
        ws.append_row(_contact_to_row(contact))
        logger.info(
            "Created contact: %s for company %s", contact.name, contact.company_id
        )
        return contact

    def update_contact(self, contact_id: str, data: dict[str, Any]) -> Contact:
        ws = self._get_worksheet()
        self._validate_headers(ws)
        all_values = ws.get_all_values()
        headers = all_values[0]

        for row_idx, row in enumerate(all_values[1:], start=2):
            row_dict = dict(zip(headers, row))
            if row_dict.get("id") == contact_id:
                row_dict.update({k: str(v) for k, v in data.items() if v is not None})
                row_dict["updated_at"] = datetime.now(UTC).isoformat()
                updated_row = [row_dict.get(h, "") for h in headers]
                ws.update(
                    f"A{row_idx}:{chr(64 + len(headers))}{row_idx}", [updated_row]
                )
                contact = _row_to_contact(row_dict)
                if contact is None:
                    raise ValueError("Update produced invalid contact data")
                return contact

        raise KeyError(f"Contact not found: {contact_id}")

    def delete_contact(self, contact_id: str) -> bool:
        ws = self._get_worksheet()
        self._validate_headers(ws)
        all_values = ws.get_all_values()
        for row_idx, row in enumerate(all_values[1:], start=2):
            if row[0] == contact_id:
                ws.delete_rows(row_idx)
                logger.info("Deleted contact: %s", contact_id)
                return True
        return False
