"""Follow-up task routes.

Routes → FollowUpService (authorized ``*_for`` methods) → FollowUpRepository.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from greenlead.api.deps import analytics_service, audit_service
from greenlead.core.i18n import get_lang_context
from greenlead.core.policy import AccessDenied
from greenlead.core.security import get_current_user_obj
from greenlead.models.schemas import FollowUpCreate, User
from greenlead.repositories import get_company_repository, get_followup_repository
from greenlead.services.analytics import FOLLOWUP_COMPLETED, FOLLOWUP_CREATED
from greenlead.services.companies import CompanyService
from greenlead.services.followups import FollowUpService, is_overdue

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/followups")
templates = Jinja2Templates(directory="templates")


def _get_service() -> FollowUpService:
    return FollowUpService(get_followup_repository(), get_company_repository())


def _get_company_service() -> CompanyService:
    return CompanyService(get_company_repository())


def _decorate(followups: list) -> list[dict]:
    """Attach a derived is_overdue flag for display without mutating the model."""
    today = datetime.now(UTC).date()
    return [{"fu": f, "overdue": is_overdue(f, today)} for f in followups]


@router.get("/", response_class=HTMLResponse)
async def list_followups(
    request: Request, user: User = Depends(get_current_user_obj)
) -> Response:
    service = _get_service()
    ctx = get_lang_context(request)
    ctx["items"] = _decorate(service.list_followups_for(user))
    return templates.TemplateResponse(
        request=request, name="followups/list.html", context=ctx
    )


@router.get("/new", response_class=HTMLResponse)
async def new_followup_form(
    request: Request, user: User = Depends(get_current_user_obj)
) -> Response:
    ctx = get_lang_context(request)
    ctx["companies"] = _get_company_service().list_companies_for(user)
    ctx["error"] = None
    return templates.TemplateResponse(
        request=request, name="followups/new.html", context=ctx
    )


@router.post("/new", response_class=HTMLResponse)
async def create_followup(
    request: Request,
    company_id: str = Form(...),
    title: str = Form(...),
    description: str = Form(default=""),
    due_date: str = Form(default=""),
    priority: str = Form(default="Medium"),
    user: User = Depends(get_current_user_obj),
) -> Response:
    service = _get_service()
    ctx = get_lang_context(request)
    try:
        followup = service.create_followup_for(
            user,
            FollowUpCreate(
                company_id=company_id,
                title=title.strip(),
                description=description.strip(),
                due_date=due_date.strip(),
                priority=priority,
            ),
        )
    except (KeyError, ValueError) as exc:
        logger.info("Follow-up creation rejected: %s", exc)
        ctx["companies"] = _get_company_service().list_companies_for(user)
        ctx["error"] = ctx["t"].get("field_required", "Invalid input.")
        ctx["form"] = {
            "company_id": company_id,
            "title": title,
            "description": description,
            "due_date": due_date,
            "priority": priority,
        }
        return templates.TemplateResponse(
            request=request, name="followups/new.html", context=ctx, status_code=422
        )
    audit_service().record(
        "followup.create",
        actor=user,
        entity_type="FollowUp",
        entity_id=followup.id,
        changes={"title": followup.title, "due_date": followup.due_date},
    )
    analytics_service().track(FOLLOWUP_CREATED, user_id=user.id)
    return RedirectResponse(url="/followups/", status_code=303)


@router.get("/{followup_id}", response_class=HTMLResponse)
async def followup_detail(
    followup_id: str, request: Request, user: User = Depends(get_current_user_obj)
) -> Response:
    service = _get_service()
    ctx = get_lang_context(request)
    try:
        followup = service.get_followup_for(user, followup_id)
    except (KeyError, AccessDenied):
        ctx["followup"] = None
        ctx["not_found"] = True
        return templates.TemplateResponse(
            request=request, name="followups/detail.html", context=ctx, status_code=404
        )
    ctx["followup"] = followup
    ctx["not_found"] = False
    ctx["overdue"] = is_overdue(followup, datetime.now(UTC).date())
    ctx["company"] = get_company_repository().get_company(followup.company_id)
    return templates.TemplateResponse(
        request=request, name="followups/detail.html", context=ctx
    )


@router.post("/{followup_id}/complete", response_class=HTMLResponse)
async def complete_followup(
    followup_id: str,
    request: Request,
    outcome: str = Form(default=""),
    user: User = Depends(get_current_user_obj),
) -> Response:
    service = _get_service()
    try:
        service.complete_followup_for(user, followup_id, outcome=outcome.strip())
        audit_service().record(
            "followup.complete",
            actor=user,
            entity_type="FollowUp",
            entity_id=followup_id,
        )
        analytics_service().track(FOLLOWUP_COMPLETED, user_id=user.id)
    except KeyError:
        logger.info("Complete requested for missing follow-up: %s", followup_id)
    return RedirectResponse(url="/followups/", status_code=303)


@router.post("/{followup_id}/delete", response_class=HTMLResponse)
async def delete_followup(
    followup_id: str, request: Request, user: User = Depends(get_current_user_obj)
) -> Response:
    try:
        _get_service().delete_followup_for(user, followup_id)
    except KeyError:
        pass
    return RedirectResponse(url="/followups/", status_code=303)
