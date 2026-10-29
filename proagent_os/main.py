from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from proagent_os import __version__
from proagent_os.api import api_router
from proagent_os.config import get_settings
from proagent_os.db import get_db
from proagent_os.ratelimit import enforce_rate_limit
from proagent_os.services import get_services

WEB_DIR = Path(__file__).parent / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_db()
    get_services()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ProAgent OS",
        description="Vertical-agnostic Pro-Agent framework (Professional / Proactive / Profitable).",
        version=__version__,
        lifespan=lifespan,
    )

    app.include_router(api_router)
    app.middleware("http")(enforce_rate_limit)

    static_dir = WEB_DIR / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "llm": settings.llm_provider}

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "version": __version__,
                "admin_hint": settings.admin_key[:4] + "…" if settings.admin_key else "",
            },
        )

    return app


app = create_app()
