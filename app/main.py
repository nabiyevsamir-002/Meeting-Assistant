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
from app.storage.db import init_db


class _NoCacheStatic(StaticFiles):
    """Statik faylları keşsiz verir — demo zamanı köhnə HTML/JS qalmasın."""

    async def get_response(self, path: str, scope):  # noqa: ANN001
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        return resp


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Tətbiqin start/stop dövrü: DB, köhnə canlı iclasların bağlanması."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    init_db()
    # LangSmith izləmə — açar veriləndə LangChain avtomatik izləyir (env dəyişənləri ilə)
    if settings.langsmith_tracing and settings.langsmith_api_key:
        import os

        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
        os.environ["LANGCHAIN_ENDPOINT"] = settings.langsmith_endpoint
        logging.getLogger("app").info("LangSmith izləmə aktivdir (layihə: %s)",
                                      settings.langsmith_project)
    # Əvvəlki işləmədən 'canlı' qalmış zombi iclasları bitmiş sayırıq —
    # panel/agent onlara qoşulub çaşmasın (yaddaşları onsuz da itib)
    from app.storage import repo as _repo

    stale = _repo.end_stale_live_meetings()
    if stale:
        logging.getLogger("app").info("Startup: %d köhnə canlı iclas bağlandı", stale)
    yield


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

    # Sadə demo UI (canlı feed izləyicisi).
    # NoCache: dev/demo zamanı brauzer köhnə HTML/JS-i keşləyib saxlamasın —
    # fayl dəyişəndən sonra adi yeniləmə (⌘R) təzəsini gətirsin.
    static_dir = Path(__file__).parent / "static"
    app.mount("/ui", _NoCacheStatic(directory=str(static_dir), html=True), name="ui")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        """Kök ünvandan UI-a yönləndirmə."""
        return RedirectResponse("/ui/index.html")

    return app


app = create_app()
