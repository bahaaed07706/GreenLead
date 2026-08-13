"""Operational Dashboard router.

Thin route calling DashboardService for consolidated metrics.
"""

import logging

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from greenlead.core.i18n import get_lang_context
from greenlead.core.security import get_current_user_obj
from greenlead.models.schemas import User
from greenlead.repositories import (
    get_company_repository,
    get_contact_repository,
    get_followup_repository,
    get_meeting_repository,
)
from greenlead.services.dashboard import DashboardService

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(
    request: Request, user: User = Depends(get_current_user_obj)
) -> Response:
    logger.debug("Dashboard accessed by %s", user.username)
    service = DashboardService(
        company_repo=get_company_repository(),
        contact_repo=get_contact_repository(),
        followup_repo=get_followup_repository(),
        meeting_repo=get_meeting_repository(),
        actor=user,  # counts/lists are scoped to what this user may see
    )
    summary = service.get_dashboard_summary()
    ctx = get_lang_context(request)
    ctx["username"] = user.username
    ctx["summary"] = summary
    return templates.TemplateResponse(
        request=request, name="dashboard.html", context=ctx
    )
