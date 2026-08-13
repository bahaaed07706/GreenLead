"""Companies CRUD routes.

Routes → CompanyService (authorized ``*_for`` methods) → CompanyRepository.
Every handler passes the acting user; the service enforces record-level access.
"""

import logging

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from greenlead.api.deps import analytics_service, audit_service
from greenlead.core import policy
from greenlead.core.i18n import get_lang_context
from greenlead.core.security import get_current_user_obj
from greenlead.models.schemas import CompanyCreate, User
from greenlead.repositories import (
    get_company_repository,
    get_contact_repository,
    get_user_repository,
)
from greenlead.services.analytics import COMPANY_CREATED
from greenlead.services.companies import CompanyService, DuplicateDomainError
from greenlead.services.contacts import ContactService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/companies")
templates = Jinja2Templates(directory="templates")


def _get_service() -> CompanyService:
    return CompanyService(get_company_repository())


def _get_contact_service() -> ContactService:
    return ContactService(get_contact_repository(), get_company_repository())


@router.get("/", response_class=HTMLResponse)
async def list_companies(
    request: Request,
    q: str | None = Query(default=None),
    user: User = Depends(get_current_user_obj),
) -> Response:
    service = _get_service()
    ctx = get_lang_context(request)
    ctx["q"] = q.strip() if q else ""
    ctx["companies"] = service.list_companies_for(user, q=q)
    return templates.TemplateResponse(
        request=request, name="companies/list.html", context=ctx
    )


@router.get("/new", response_class=HTMLResponse)
async def new_company_form(
    request: Request, user: User = Depends(get_current_user_obj)
) -> Response:
    ctx = get_lang_context(request)
    ctx["error"] = None
    return templates.TemplateResponse(
        request=request, name="companies/new.html", context=ctx
    )


@router.post("/new", response_class=HTMLResponse)
async def create_company(
    request: Request,
    name_en: str = Form(...),
    name_ar: str = Form(default=""),
    domain: str = Form(default=""),
    sector: str = Form(default=""),
    city: str = Form(default=""),
    description: str = Form(default=""),
    user: User = Depends(get_current_user_obj),
) -> Response:
    service = _get_service()
    ctx = get_lang_context(request)
    form = {
        "name_en": name_en,
        "name_ar": name_ar,
        "domain": domain,
        "sector": sector,
        "city": city,
        "description": description,
    }

    if not name_en.strip():
        ctx["error"] = ctx["t"].get("field_required", "Required.")
        ctx["form"] = form
        return templates.TemplateResponse(
            request=request, name="companies/new.html", context=ctx, status_code=422
        )

    try:
        company = service.create_company_for(
            user,
            CompanyCreate(
                name_en=name_en.strip(),
                name_ar=name_ar.strip(),
                domain=domain.strip(),
                sector=sector.strip(),
                city=city.strip(),
                description=description.strip(),
            ),
        )
    except DuplicateDomainError:
        ctx["error"] = ctx["t"].get("duplicate_domain", "Duplicate domain.")
        ctx["form"] = form
        return templates.TemplateResponse(
            request=request, name="companies/new.html", context=ctx, status_code=409
        )

    audit_service().record(
        "company.create",
        actor=user,
        entity_type="Company",
        entity_id=company.id,
        changes={"name_en": company.name_en, "domain": company.domain},
    )
    analytics_service().track(COMPANY_CREATED, user_id=user.id)
    return RedirectResponse(url=f"/companies/{company.id}", status_code=303)


@router.get("/{company_id}", response_class=HTMLResponse)
async def company_detail(
    company_id: str,
    request: Request,
    user: User = Depends(get_current_user_obj),
) -> Response:
    service = _get_service()
    contact_service = _get_contact_service()
    ctx = get_lang_context(request)
    try:
        company = service.get_company_for(user, company_id)
    except (KeyError, policy.AccessDenied):
        # Missing AND forbidden return the SAME 404, so an employee cannot
        # enumerate which company ids exist by probing URLs.
        ctx["company"] = None
        ctx["contacts"] = []
        ctx["not_found"] = True
        return templates.TemplateResponse(
            request=request, name="companies/detail.html", context=ctx, status_code=404
        )
    contacts = contact_service.list_contacts_for(user, company_id)
    ctx["company"] = company
    ctx["contacts"] = contacts
    ctx["not_found"] = False
    ctx["can_reassign"] = policy.can_reassign(user)
    if policy.can_reassign(user):
        ctx["assignable_users"] = [
            u for u in get_user_repository().list_users() if u.is_active
        ]
    ctx["owner"] = (
        get_user_repository().get_user(company.owner_id) if company.owner_id else None
    )
    return templates.TemplateResponse(
        request=request, name="companies/detail.html", context=ctx
    )


@router.post("/{company_id}/reassign", response_class=HTMLResponse)
async def reassign_company(
    company_id: str,
    request: Request,
    new_owner_id: str = Form(...),
    user: User = Depends(get_current_user_obj),
) -> Response:
    service = _get_service()
    # policy.require_reassign inside reassign_for raises AccessDenied -> 403 page.
    service.reassign_for(user, company_id, new_owner_id)
    audit_service().record(
        "company.reassign",
        actor=user,
        entity_type="Company",
        entity_id=company_id,
        changes={"new_owner_id": new_owner_id},
    )
    return RedirectResponse(url=f"/companies/{company_id}", status_code=303)
