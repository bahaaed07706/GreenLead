import logging

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from greenlead.api.deps import analytics_service, audit_service
from greenlead.core.config import Settings, get_settings
from greenlead.core.i18n import get_lang_context
from greenlead.core.security import create_session_token, limiter
from greenlead.repositories import get_user_repository
from greenlead.services.analytics import LOGIN_SUCCESS
from greenlead.services.users import UserService

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request) -> Response:
    if request.cookies.get("session"):
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    ctx = get_lang_context(request)
    return templates.TemplateResponse(request=request, name="login.html", context=ctx)


@router.post("/login", response_class=HTMLResponse)
@limiter.limit("5/minute")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    settings: Settings = Depends(get_settings),
) -> Response:
    ctx = get_lang_context(request)
    service = UserService(get_user_repository())
    service.ensure_bootstrap_admin(settings)
    user = service.authenticate(username, password)
    if user is None:
        logger.warning(f"Failed login attempt for username: {username}")
        audit_service().record(
            "auth.login_failed",
            actor_username=username,
            outcome="failure",
        )
        ctx["error"] = ctx["t"]["invalid_credentials"]
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context=ctx,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    logger.info(f"Successful login for {username}")
    audit_service().record(
        "auth.login_success", actor=user, entity_type="User", entity_id=user.id
    )
    analytics_service().track(LOGIN_SUCCESS, user_id=user.id)
    token = create_session_token(username)
    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="session",
        value=token,
        httponly=True,
        secure=(settings.app_env == "production"),
        samesite="lax",
        max_age=86400 * 7,
    )
    return response


@router.post("/logout")
@router.get("/logout")
async def logout(request: Request) -> Response:
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="session")
    return response


@router.get("/set-language")
async def set_language(lang: str, request: Request) -> Response:
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(url=referer, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="lang",
        value=lang if lang in ["ar", "en"] else "ar",
        max_age=86400 * 365,
        samesite="lax",
    )
    return response
