from fastapi import FastAPI

from filmoteka.api.health import router as health_router
from filmoteka.infrastructure.settings import settings


def create_app() -> FastAPI:
    app = FastAPI(title="Filmoteka", version=settings.version)
    app.include_router(health_router)
    return app


app = create_app()
