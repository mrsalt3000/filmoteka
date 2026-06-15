import logging
import time as _time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from filmoteka.api.admin import router as admin_router
from filmoteka.api.auth import router as auth_router
from filmoteka.api.catalog import router as catalog_router
from filmoteka.api.health import router as health_router
from filmoteka.api.media import router as media_router
from filmoteka.api.series import router as series_router
from filmoteka.api.users import router as users_router
from filmoteka.domain.access.models import User
from filmoteka.domain.access.service import hash_password
from filmoteka.domain.tasks import (
    models as _tasks_models,  # noqa: F401 — register models for Alembic
)
from filmoteka.infrastructure.database import SessionLocal
from filmoteka.infrastructure.library_config import load_library_config
from filmoteka.infrastructure.logging_config import setup_json_logging
from filmoteka.infrastructure.settings import settings

# ── Structured JSON logging ────────────────────────────────────
setup_json_logging("INFO")


class RequestLogMiddleware:
    """ASGI middleware that logs HTTP requests as JSON."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = _time.time()
        response_status = [200]

        async def _send(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_status[0] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception:
            _log_request(scope, 500, start)
            raise

        _log_request(scope, response_status[0], start)


def _log_request(scope: Scope, status: int, start: float) -> None:
    duration = _time.time() - start
    method = scope.get("method", "?")
    path = scope.get("path", "?")
    query = scope.get("query_string", b"").decode()
    full_path = f"{path}?{query}" if query else path
    logger = logging.getLogger("filmoteka.access")
    logger.info(
        "request",
        extra={
            "extra_fields": {
                "method": method,
                "path": full_path,
                "status": status,
                "duration_ms": round(duration * 1000, 1),
            }
        },
    )


def seed_dev_admin() -> None:
    """Create default admin user ``mrsalt3000`` / ``dev`` if not present.

    Intended for local development — idempotent, safe to call on every startup.
    """
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == "mrsalt3000").first()
        if existing is not None:
            return

        user = User(
            username="mrsalt3000",
            hashed_password=hash_password("dev"),
            role="admin",
        )
        db.add(user)
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Load library config and seed dev admin on startup."""

    spec_path = settings.library_spec_path
    if not spec_path.is_absolute():
        spec_path = Path.cwd() / spec_path

    config = load_library_config(spec_path)
    config = config.with_overrides(
        downloads_root=settings.downloads_root,
        library_root=settings.library_root,
    )
    app.state.library_config = config

    seed_dev_admin()

    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Filmoteka", version=settings.version, lifespan=_lifespan)
    app.add_middleware(RequestLogMiddleware)  # type: ignore[arg-type]
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(catalog_router)
    app.include_router(media_router)
    app.include_router(series_router)
    app.include_router(users_router)

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.is_dir():
        index = static_dir / "index.html"
        app.mount(
            "/static",
            StaticFiles(directory=str(static_dir)),
            name="static",
        )

        # Serve index.html for root and SPA catch-all
        @app.get("/")
        async def serve_root() -> FileResponse:
            return FileResponse(str(index))

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str) -> FileResponse:
            # Don't interfere with API paths — FastAPI checks these last
            return FileResponse(str(index))

    return app


app = create_app()
