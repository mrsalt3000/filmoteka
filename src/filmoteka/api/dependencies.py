"""Shared FastAPI dependencies."""

from fastapi import Request

from filmoteka.infrastructure.library_config import LibraryConfig


def get_library_config(request: Request) -> LibraryConfig:
    """Dependency: return the ``LibraryConfig`` stored in app state.

    Requires the lifespan hook in ``app.py`` to have loaded it on startup.
    """
    config: LibraryConfig = request.app.state.library_config
    return config
