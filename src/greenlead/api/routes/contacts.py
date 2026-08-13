"""Contacts CRUD router.

Routes → ContactService (authorized ``*_for`` methods) → ContactRepository.
Contact access derives from the parent Company (enforced in the service).
"""

import logging

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from greenlead.api.deps import analytics_service, audit_service
from greenlead.core import policy
from greenlead.core.i18n import get_lang_context
from greenlead.core.security import get_current_user_obj
from greenlead.models.schemas import ContactCreate, User
from greenlead.repositories import get_company_repository, get_contact_repository
from greenlead.services.analytics import CONTACT_CREATED, DECISION_MAKER_ADDED
from greenlead.services.contacts import ContactService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/companies")
templates = Jinja2Templates(directory="templates")


def _get_service() -> ContactService:
    return ContactService(get_contact_repository(), get_company_repository())


@router.get("/{company_id}/contacts/new", response_class=HTMLResponse)
async def new_contact_form(
    company_id: str,
    request: Request,
    user: User = Depends(get_current_user_obj),
) -> Response:
    # Enforce access to the parent company; AccessDenied -> 403 page.
    company = get_company_repository().get_company(company_id)
    if company is not None:
        policy.require_edit(user, company.owner_id)
    ctx = get_lang_context(request)
    ctx["company"] = company
    ctx["not_found"] = company is None
    ctx["error"] = None
    return templates.TemplateResponse(
        request=request, name="contacts/new.html", context=ctx
    )


@router.post("/{company_id}/contacts/new", response_class=HTMLResponse)
async def create_contact(
    company_id: str,
    request: Request,
    name: str = Form(...),
    title: str = Form(default=""),
    email: str = Form(default=""),
    phone: str = Form(default=""),
    relationship_level: str = Form(default="Contact"),
    is_decision_maker: bool = Form(default=False),
    source_url: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user_obj),
) -> Response:
    service = _get_service()
    company = get_company_repository().get_company(company_id)
    ctx = get_lang_context(request)
    ctx["company"] = company
    ctx["not_found"] = company is None

    if not name.strip():
        ctx["error"] = ctx["t"].get("field_required", "Required.")
        ctx["form"] = {
            "name": name,
            "title": title,
            "email": email,
            "phone": phone,
            "relationship_level": relationship_level,
            "is_decision_maker": is_decision_maker,
            "source_url": source_url,
            "notes": notes,
        }
        return templates.TemplateResponse(
            request=request, name="contacts/new.html", context=ctx, status_code=422
        )

    try:
        contact = service.create_contact_for(
            user,
            ContactCreate(
                company_id=company_id,
                name=name.strip(),
                title=title.strip(),
                email=email.strip(),
                phone=phone.strip(),
                relationship_level=relationship_level.strip(),
                is_decision_maker=is_decision_maker,
                source_url=source_url.strip(),
                notes=notes.strip(),
            ),
        )
    except KeyError:
        ctx["not_found"] = True
        return templates.TemplateResponse(
            request=request, name="contacts/new.html", context=ctx, status_code=404
        )

    audit_service().record(
        "contact.create",
        actor=user,
        entity_type="Contact",
        entity_id=contact.id,
        changes={"name": contact.name, "is_decision_maker": is_decision_maker},
    )
    analytics_service().track(CONTACT_CREATED, user_id=user.id)
    if is_decision_maker:
        analytics_service().track(DECISION_MAKER_ADDED, user_id=user.id)
        audit_service().record(
            "contact.decision_maker_change",
            actor=user,
            entity_type="Contact",
            entity_id=contact.id,
            changes={"is_decision_maker": True},
        )
    return RedirectResponse(url=f"/companies/{company_id}", status_code=303)


@router.get("/{company_id}/contacts/{contact_id}/edit", response_class=HTMLResponse)
async def edit_contact_form(
    company_id: str,
    contact_id: str,
    request: Request,
    user: User = Depends(get_current_user_obj),
) -> Response:
    service = _get_service()
    company = get_company_repository().get_company(company_id)
    try:
        contact = service.get_contact_for(user, contact_id)
    except KeyError:
        contact = None
    ctx = get_lang_context(request)
    ctx["company"] = company
    ctx["contact"] = contact
    ctx["not_found"] = company is None or contact is None
    ctx["error"] = None
    return templates.TemplateResponse(
        request=request, name="contacts/edit.html", context=ctx
    )


@router.post("/{company_id}/contacts/{contact_id}/edit", response_class=HTMLResponse)
async def update_contact(
    company_id: str,
    contact_id: str,
    request: Request,
    name: str = Form(...),
    title: str = Form(default=""),
    email: str = Form(default=""),
    phone: str = Form(default=""),
    relationship_level: str = Form(default="Contact"),
    is_decision_maker: bool = Form(default=False),
    source_url: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user_obj),
) -> Response:
    service = _get_service()
    company = get_company_repository().get_company(company_id)
    ctx = get_lang_context(request)
    ctx["company"] = company

    if not name.strip():
        ctx["error"] = ctx["t"].get("field_required", "Required.")
        ctx["contact"] = {
            "id": contact_id,
            "company_id": company_id,
            "name": name,
            "title": title,
            "email": email,
            "phone": phone,
            "relationship_level": relationship_level,
            "is_decision_maker": is_decision_maker,
            "source_url": source_url,
            "notes": notes,
        }
        ctx["not_found"] = False
        return templates.TemplateResponse(
            request=request, name="contacts/edit.html", context=ctx, status_code=422
        )

    try:
        service.update_contact_for(
            user,
            contact_id,
            {
                "name": name.strip(),
                "title": title.strip(),
                "email": email.strip(),
                "phone": phone.strip(),
                "relationship_level": relationship_level.strip(),
                "is_decision_maker": is_decision_maker,
                "source_url": source_url.strip(),
                "notes": notes.strip(),
            },
        )
    except KeyError:
        ctx["not_found"] = True
        return templates.TemplateResponse(
            request=request, name="contacts/edit.html", context=ctx, status_code=404
        )

    audit_service().record(
        "contact.update",
        actor=user,
        entity_type="Contact",
        entity_id=contact_id,
        changes={"name": name.strip()},
    )
    return RedirectResponse(url=f"/companies/{company_id}", status_code=303)


@router.post("/{company_id}/contacts/{contact_id}/delete")
async def delete_contact(
    company_id: str,
    contact_id: str,
    user: User = Depends(get_current_user_obj),
) -> Response:
    service = _get_service()
    try:
        service.delete_contact_for(user, contact_id)
        audit_service().record(
            "contact.delete",
            actor=user,
            entity_type="Contact",
            entity_id=contact_id,
        )
    except KeyError:
        pass
    return RedirectResponse(url=f"/companies/{company_id}", status_code=303)
