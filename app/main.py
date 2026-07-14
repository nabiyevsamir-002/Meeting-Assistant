"""FastAPI giriş nöqtəsi.

İşə salmaq:  uvicorn app.main:app --reload
UI:          http://localhost:8000/ui/index.html
API sənədi:  http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.config import get_settings
from app.services.scheduler import prepare_upcoming_meetings, start_scheduler, stop_scheduler
from app.storage.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Tətbiqin start/stop dövrü: DB, planlayıcı, ilkin təqvim yoxlaması."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    init_db()
    if settings.scheduler_enabled:
        start_scheduler()
        # Startup-da bir dəfə dərhal yoxlayırıq (interval gözləmədən)
        prepare_upcoming_meetings()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    """Tətbiqi qurur — router-lər, statik fayllar, lifespan."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        description="Onlayn iclaslarda qeyd götürmə ehtiyacını aradan qaldıran AI köməkçi",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(api_router)

    # Sadə demo UI (canlı feed izləyicisi)
    static_dir = Path(__file__).parent / "static"
    app.mount("/ui", StaticFiles(directory=str(static_dir), html=True), name="ui")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        """Kök ünvandan UI-a yönləndirmə."""
        return RedirectResponse("/ui/index.html")

    return app


app = create_app()
