"""Meeting routes.

Routes → MeetingService (authorized ``*_for`` methods) → MeetingRepository.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Query, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from greenlead.api.deps import analytics_service, audit_service
from greenlead.core.i18n import get_lang_context
from greenlead.core.policy import AccessDenied
from greenlead.core.security import get_current_user_obj
from greenlead.models.schemas import MeetingCreate, User
from greenlead.repositories import (
    get_company_repository,
    get_contact_repository,
    get_meeting_repository,
)
from greenlead.services.analytics import MEETING_CREATED, MEETING_OUTCOME_ADDED
from greenlead.services.companies import CompanyService
from greenlead.services.meetings import MeetingService, is_missing_outcome

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meetings")
templates = Jinja2Templates(directory="templates")


def _get_service() -> MeetingService:
    return MeetingService(
        get_meeting_repository(),
        get_company_repository(),
        get_contact_repository(),
    )


def _visible_contacts(user: User) -> list[dict]:
    """Contacts of companies the actor may see — never the whole directory."""
    companies = CompanyService(get_company_repository()).list_companies_for(user)
    contact_repo = get_contact_repository()
    out: list[dict] = []
    for company in companies:
        for contact in contact_repo.list_contacts_by_company(company.id):
            out.append({"contact": contact, "company_name": company.name_en})
    return out


@router.get("/", response_class=HTMLResponse)
async def list_meetings(
    request: Request,
    view: str = Query(default="all"),
    user: User = Depends(get_current_user_obj),
) -> Response:
    service = _get_service()
    today = datetime.now(UTC).date()
    if view == "today":
        meetings = service.today_for(user, today)
    elif view == "upcoming":
        meetings = service.upcoming_for(user, today)
    else:
        meetings = service.list_meetings_for(user)
    ctx = get_lang_context(request)
    ctx["view"] = view
    ctx["items"] = [
        {"m": m, "missing_outcome": is_missing_outcome(m, today)} for m in meetings
    ]
    return templates.TemplateResponse(
        request=request, name="meetings/list.html", context=ctx
    )


@router.get("/new", response_class=HTMLResponse)
async def new_meeting_form(
    request: Request, user: User = Depends(get_current_user_obj)
) -> Response:
    ctx = get_lang_context(request)
    ctx["companies"] = CompanyService(get_company_repository()).list_companies_for(user)
    ctx["contacts"] = _visible_contacts(user)
    ctx["error"] = None
    return templates.TemplateResponse(
        request=request, name="meetings/new.html", context=ctx
    )


@router.post("/new", response_class=HTMLResponse)
async def create_meeting(
    request: Request,
    company_id: str = Form(...),
    subject: str = Form(...),
    contact_id: str = Form(default=""),
    description: str = Form(default=""),
    meeting_date: str = Form(default=""),
    start_time: str = Form(default=""),
    end_time: str = Form(default=""),
    meeting_type: str = Form(default="Online"),
    meeting_url: str = Form(default=""),
    location: str = Form(default=""),
    participants: str = Form(default=""),
    agenda: str = Form(default=""),
    user: User = Depends(get_current_user_obj),
) -> Response:
    service = _get_service()
    ctx = get_lang_context(request)
    try:
        meeting = service.create_meeting_for(
            user,
            MeetingCreate(
                company_id=company_id,
                contact_id=contact_id,
                subject=subject.strip(),
                description=description.strip(),
                meeting_date=meeting_date.strip(),
                start_time=start_time.strip(),
                end_time=end_time.strip(),
                meeting_type=meeting_type,
                meeting_url=meeting_url.strip(),
                location=location.strip(),
                participants=participants.strip(),
                agenda=agenda.strip(),
            ),
        )
    except (KeyError, ValueError) as exc:
        logger.info("Meeting creation rejected: %s", exc)
        ctx["companies"] = CompanyService(get_company_repository()).list_companies_for(
            user
        )
        ctx["contacts"] = _visible_contacts(user)
        ctx["error"] = str(exc)
        ctx["form"] = {
            "company_id": company_id,
            "contact_id": contact_id,
            "subject": subject,
            "description": description,
            "meeting_date": meeting_date,
            "start_time": start_time,
            "end_time": end_time,
            "meeting_type": meeting_type,
            "meeting_url": meeting_url,
            "location": location,
            "participants": participants,
            "agenda": agenda,
        }
        return templates.TemplateResponse(
            request=request, name="meetings/new.html", context=ctx, status_code=422
        )
    audit_service().record(
        "meeting.create",
        actor=user,
        entity_type="Meeting",
        entity_id=meeting.id,
        changes={"subject": meeting.subject, "date": meeting.meeting_date},
    )
    analytics_service().track(MEETING_CREATED, user_id=user.id)
    return RedirectResponse(url="/meetings/", status_code=303)


@router.get("/{meeting_id}", response_class=HTMLResponse)
async def meeting_detail(
    meeting_id: str, request: Request, user: User = Depends(get_current_user_obj)
) -> Response:
    service = _get_service()
    ctx = get_lang_context(request)
    try:
        meeting = service.get_meeting_for(user, meeting_id)
    except (KeyError, AccessDenied):
        ctx["meeting"] = None
        ctx["not_found"] = True
        return templates.TemplateResponse(
            request=request, name="meetings/detail.html", context=ctx, status_code=404
        )
    ctx["meeting"] = meeting
    ctx["not_found"] = False
    ctx["company"] = get_company_repository().get_company(meeting.company_id)
    return templates.TemplateResponse(
        request=request, name="meetings/detail.html", context=ctx
    )


@router.get("/{meeting_id}/ics", response_class=PlainTextResponse)
async def meeting_ics(
    meeting_id: str, user: User = Depends(get_current_user_obj)
) -> Response:
    service = _get_service()
    try:
        meeting = service.get_meeting_for(user, meeting_id)
    except (KeyError, AccessDenied):
        return PlainTextResponse("Not found", status_code=404)
    return PlainTextResponse(
        service.to_ics(meeting),
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="meeting-{meeting.id}.ics"'
        },
    )


@router.post("/{meeting_id}/complete", response_class=HTMLResponse)
async def complete_meeting(
    meeting_id: str,
    request: Request,
    outcome: str = Form(default=""),
    followup_action: str = Form(default=""),
    user: User = Depends(get_current_user_obj),
) -> Response:
    try:
        _get_service().complete_meeting_for(
            user,
            meeting_id,
            outcome=outcome.strip(),
            followup_action=followup_action.strip(),
        )
        audit_service().record(
            "meeting.complete",
            actor=user,
            entity_type="Meeting",
            entity_id=meeting_id,
            changes={"outcome": outcome.strip()},
        )
        if outcome.strip():
            analytics_service().track(MEETING_OUTCOME_ADDED, user_id=user.id)
    except KeyError:
        logger.info("Complete requested for missing meeting: %s", meeting_id)
    return RedirectResponse(url=f"/meetings/{meeting_id}", status_code=303)


@router.post("/{meeting_id}/cancel", response_class=HTMLResponse)
async def cancel_meeting(
    meeting_id: str, request: Request, user: User = Depends(get_current_user_obj)
) -> Response:
    try:
        _get_service().cancel_meeting_for(user, meeting_id)
        audit_service().record(
            "meeting.cancel",
            actor=user,
            entity_type="Meeting",
            entity_id=meeting_id,
        )
    except KeyError:
        logger.info("Cancel requested for missing meeting: %s", meeting_id)
    return RedirectResponse(url=f"/meetings/{meeting_id}", status_code=303)


@router.post("/{meeting_id}/delete", response_class=HTMLResponse)
async def delete_meeting(
    meeting_id: str, request: Request, user: User = Depends(get_current_user_obj)
) -> Response:
    try:
        _get_service().delete_meeting_for(user, meeting_id)
    except KeyError:
        pass
    return RedirectResponse(url="/meetings/", status_code=303)
