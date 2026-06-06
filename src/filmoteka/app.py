from fastapi import FastAPI

from filmoteka.api.admin import router as admin_router
from filmoteka.api.auth import router as auth_router
from filmoteka.api.catalog import router as catalog_router
from filmoteka.api.health import router as health_router
from filmoteka.infrastructure.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(title="Filmoteka", version=settings.version)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(catalog_router)
    return app


app = create_app()
