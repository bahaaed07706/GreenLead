"""Admin-only Audit Log viewer (read-only) with filters and pagination."""

import logging

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from greenlead.api.deps import audit_service
from greenlead.core.i18n import get_lang_context
from greenlead.core.security import require_role
from greenlead.services.audit import ACTIONS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")

admin_only = require_role("admin")

PAGE_SIZE = 25


@router.get("/audit", response_class=HTMLResponse)
async def audit_log(
    request: Request,
    actor: str = Query(default=""),
    action: str = Query(default=""),
    entity_type: str = Query(default=""),
    outcome: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    _: str = Depends(admin_only),
) -> Response:
    service = audit_service()
    filters: dict[str, str | None] = {
        "actor": actor or None,
        "action": action or None,
        "entity_type": entity_type or None,
        "outcome": outcome or None,
        "date_from": date_from or None,
        "date_to": date_to or None,
    }
    total = service.count_events(**filters)  # type: ignore[arg-type]
    events = service.list_events(
        limit=PAGE_SIZE,
        offset=(page - 1) * PAGE_SIZE,
        **filters,  # type: ignore[arg-type]
    )
    ctx = get_lang_context(request)
    ctx["events"] = events
    ctx["actions"] = sorted(ACTIONS)
    ctx["outcomes"] = ["success", "denied", "failure"]
    ctx["filters"] = {
        "actor": actor,
        "action": action,
        "entity_type": entity_type,
        "outcome": outcome,
        "date_from": date_from,
        "date_to": date_to,
    }
    ctx["page"] = page
    ctx["total"] = total
    ctx["has_next"] = page * PAGE_SIZE < total
    ctx["has_prev"] = page > 1
    return templates.TemplateResponse(
        request=request, name="admin/audit.html", context=ctx
    )
