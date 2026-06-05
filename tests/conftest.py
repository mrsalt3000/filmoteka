"""Test configuration and fixtures.

Sets required environment variables before any app imports so that
pydantic-settings picks them up at import time.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

# Required env vars — set before importing app/settings
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://u:p@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef")

from filmoteka.app import app  # noqa: E402
from filmoteka.infrastructure.settings import settings  # noqa: E402


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def test_settings() -> settings.__class__:  # type: ignore[misc]
    return settings
