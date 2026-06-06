from fastapi import FastAPI

from filmoteka.api.admin import router as admin_router
from filmoteka.api.auth import router as auth_router
from filmoteka.api.catalog import router as catalog_router
from filmoteka.api.health import router as health_router
from filmoteka.api.media import router as media_router
from filmoteka.api.users import router as users_router
from filmoteka.infrastructure.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(title="Filmoteka", version=settings.version)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(catalog_router)
    app.include_router(media_router)
    app.include_router(users_router)
    return app


app = create_app()
