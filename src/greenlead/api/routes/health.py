import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from greenlead.core.config import Settings, get_settings
from greenlead.repositories import check_db

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health_check(
    settings: Settings = Depends(get_settings),
) -> dict:
    logger.debug("Health endpoint called")
    return {"status": "ok", "service": "greenlead", "environment": settings.app_env}


@router.get("/ready")
async def readiness_check() -> JSONResponse:
    """Readiness probe: verifies the configured persistence backend is reachable."""
    ok, backend = check_db()
    status_code = 200 if ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if ok else "not_ready", "backend": backend},
    )
