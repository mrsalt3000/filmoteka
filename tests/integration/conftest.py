"""Integration test fixtures — clean PostgreSQL database per session."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

# Test database name (separate from the main filmoteka DB)
TEST_DB_NAME = "filmoteka_test"

# Derive test DB URL from the main DATABASE_URL
_BASE_DB_URL = "postgresql+psycopg://filmoteka:filmoteka@localhost:5432"

ADMIN_URL = f"{_BASE_DB_URL}/postgres"
TEST_DATABASE_URL = f"{_BASE_DB_URL}/{TEST_DB_NAME}"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _recreate_database() -> None:
    """Drop and recreate the test database from scratch."""
    engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{TEST_DB_NAME}'
              AND pid <> pg_backend_pid()
        """))
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME}"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    engine.dispose()


def _run_alembic_upgrade() -> None:
    """Run all migrations against the test database."""
    from alembic.command import upgrade
    from alembic.config import Config

    alembic_cfg = Config(PROJECT_ROOT / "alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    upgrade(alembic_cfg, "head")


# ---------------------------------------------------------------------------
# Session-scoped fixtures — share DB & engine across all integration tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def _test_database() -> Generator[None, None, None]:
    """Create test DB + apply migrations once per session; drop on teardown."""
    _recreate_database()
    _run_alembic_upgrade()
    yield
    _recreate_database()


@pytest.fixture(scope="session")
def db_engine(_test_database: None) -> Generator[Engine, None, None]:
    """Engine connected to the prepared test database."""
    engine = create_engine(TEST_DATABASE_URL)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def alembic_config(_test_database: None) -> Generator:
    """Alembic Config pointing at the test database."""
    from alembic.config import Config

    cfg = Config(PROJECT_ROOT / "alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    yield cfg


# ---------------------------------------------------------------------------
# Per-test fixtures — isolated sessions with rollback
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    """Provide a session rolled back after each test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
