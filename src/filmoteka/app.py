from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from filmoteka.api.admin import router as admin_router
from filmoteka.api.auth import router as auth_router
from filmoteka.api.catalog import router as catalog_router
from filmoteka.api.health import router as health_router
from filmoteka.api.media import router as media_router
from filmoteka.api.users import router as users_router
from filmoteka.infrastructure.library_config import load_library_config
from filmoteka.infrastructure.settings import settings


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Load library config on startup; store in app state."""

    spec_path = settings.library_spec_path
    if not spec_path.is_absolute():
        spec_path = Path.cwd() / spec_path

    config = load_library_config(spec_path)
    config = config.with_overrides(
        downloads_root=settings.downloads_root,
        library_root=settings.library_root,
    )
    app.state.library_config = config
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Filmoteka", version=settings.version, lifespan=_lifespan)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(catalog_router)
    app.include_router(media_router)
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
