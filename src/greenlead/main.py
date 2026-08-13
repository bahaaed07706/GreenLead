import uvicorn

from greenlead.application import create_app
from greenlead.core.config import get_settings

app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "greenlead.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_debug,
    )
