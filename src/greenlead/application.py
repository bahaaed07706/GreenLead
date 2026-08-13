import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from greenlead.api.routes import (
    admin,
    audit,
    auth,
    companies,
    contacts,
    dashboard,
    followups,
    health,
    meetings,
)
from greenlead.core.config import get_settings
from greenlead.core.i18n import get_lang_context
from greenlead.core.logging import setup_logging
from greenlead.core.policy import AccessDenied
from greenlead.core.security import limiter

logger = logging.getLogger(__name__)
_templates = Jinja2Templates(directory="templates")


async def _access_denied_handler(request: Request, exc: Exception) -> HTMLResponse:
    """Render a bilingual 403 page. Reveals nothing about the record's existence."""
    ctx = get_lang_context(request)
    return _templates.TemplateResponse(
        request=request, name="errors/403.html", context=ctx, status_code=403
    )


def create_app() -> FastAPI:
    # 1. Load config
    settings = get_settings()

    # 2. Setup logging
    setup_logging(settings.log_level)
    logger.info(f"Starting {settings.app_name} in {settings.app_env} mode")

    # 3. Create app instance
    app = FastAPI(
        title=settings.app_name,
        description=settings.app_description,
        version="0.1.0",
    )

    # 4. Setup Rate Limiter + authorization error page
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore
    app.add_exception_handler(AccessDenied, _access_denied_handler)  # type: ignore

    # 5. Include routers
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(companies.router)
    app.include_router(contacts.router)
    app.include_router(followups.router)
    app.include_router(meetings.router)
    app.include_router(admin.router)
    app.include_router(audit.router)

    # 6. Mount static files
    app.mount("/static", StaticFiles(directory="static"), name="static")

    return app
