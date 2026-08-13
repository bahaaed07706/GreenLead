"""Admin user-management routes (admin role only).

Routes -> UserService -> UserRepository. Authorization is enforced here via the
require_role("admin") dependency, never only in templates.
"""

import logging

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from greenlead.api.deps import audit_service
from greenlead.core.i18n import get_lang_context
from greenlead.core.security import require_role
from greenlead.models.schemas import UserCreate
from greenlead.repositories import get_user_repository
from greenlead.services.users import VALID_ROLES, UserService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")

admin_only = require_role("admin")


def _service() -> UserService:
    return UserService(get_user_repository())


@router.get("/users", response_class=HTMLResponse)
async def list_users(request: Request, _: str = Depends(admin_only)) -> Response:
    ctx = get_lang_context(request)
    ctx["users"] = _service().list_users()
    ctx["roles"] = sorted(VALID_ROLES)
    return templates.TemplateResponse(
        request=request, name="admin/users.html", context=ctx
    )


@router.get("/users/new", response_class=HTMLResponse)
async def new_user_form(request: Request, _: str = Depends(admin_only)) -> Response:
    ctx = get_lang_context(request)
    ctx["roles"] = sorted(VALID_ROLES)
    ctx["error"] = None
    return templates.TemplateResponse(
        request=request, name="admin/new_user.html", context=ctx
    )


@router.post("/users/new", response_class=HTMLResponse)
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    name: str = Form(default=""),
    email: str = Form(default=""),
    role: str = Form(default="employee"),
    actor: str = Depends(admin_only),
) -> Response:
    ctx = get_lang_context(request)
    try:
        created = _service().create_user(
            UserCreate(
                username=username.strip(),
                password=password,
                name=name.strip(),
                email=email.strip(),
                role=role,
                created_by=actor,
            )
        )
    except ValueError as exc:
        logger.info("User creation rejected: %s", exc)
        ctx["roles"] = sorted(VALID_ROLES)
        ctx["error"] = str(exc)
        ctx["form"] = {"username": username, "name": name, "email": email, "role": role}
        return templates.TemplateResponse(
            request=request, name="admin/new_user.html", context=ctx, status_code=422
        )
    audit_service().record(
        "user.create",
        actor_username=actor,
        entity_type="User",
        entity_id=created.id,
        changes={"username": created.username, "role": created.role},
    )
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/deactivate", response_class=HTMLResponse)
async def deactivate_user(
    user_id: str, request: Request, actor: str = Depends(admin_only)
) -> Response:
    service = _service()
    target = get_user_repository().get_user(user_id)
    # Guard: an admin cannot deactivate their own account (avoids self-lockout).
    if target is not None and target.username != actor:
        service.set_active(user_id, False)
        logger.info("User deactivated: %s by %s", target.username, actor)
        audit_service().record(
            "user.deactivate",
            actor_username=actor,
            entity_type="User",
            entity_id=user_id,
            changes={"username": target.username},
        )
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/activate", response_class=HTMLResponse)
async def activate_user(
    user_id: str, request: Request, actor: str = Depends(admin_only)
) -> Response:
    _service().set_active(user_id, True)
    audit_service().record(
        "user.activate",
        actor_username=actor,
        entity_type="User",
        entity_id=user_id,
    )
    return RedirectResponse(url="/admin/users", status_code=303)
