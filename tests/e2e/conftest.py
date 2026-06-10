"""E2E test fixtures — shared with integration tests."""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

# Ensure tests/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from filmoteka.app import create_app  # noqa: E402
from filmoteka.infrastructure.database import get_db  # noqa: E402

# Use the integration conftest's session-scoped fixtures
from integration.conftest import (  # noqa: E402
    TEST_DATABASE_URL,
    _test_database,
    db_engine,
)


@pytest.fixture
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    """Per-test DB session with rollback (same as integration tests)."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """FastAPI TestClient connected to the test database."""
    app = create_app()

    def _override() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
