"""Integration tests for admin-only endpoints and role enforcement."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from filmoteka.app import create_app
from filmoteka.infrastructure.database import get_db

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient with DB dependency overridden to the integration test DB."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c


def _create_user(
    client: TestClient, username: str, password: str
) -> str:
    """Register a user via the API and return the access token."""
    resp = client.post(
        "/auth/register",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 201
    token: str = resp.json()["access_token"]
    return token


class TestAdminHealth:
    """GET /admin/health — role enforcement."""

    def test_admin_can_access(self, client: TestClient, db_session: Session) -> None:
        """Register as a user, then promote to admin via DB."""
        token = _create_user(client, "admin_promote", "somepass")
        user_id = _get_user_id(db_session, "admin_promote")
        db_session.execute(
            text("UPDATE users SET role = 'admin' WHERE id = :uid"),
            {"uid": user_id},
        )
        db_session.commit()

        resp = client.get(
            "/admin/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["role"] == "admin"
        assert body["username"] == "admin_promote"

    def test_regular_user_gets_403(
        self, client: TestClient
    ) -> None:
        token = _create_user(client, "regular_user", "userpass")
        resp = client.get(
            "/admin/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
        assert "Insufficient permissions" in resp.json()["detail"]

    def test_without_token_gets_401(
        self, client: TestClient
    ) -> None:
        resp = client.get("/admin/health")
        assert resp.status_code == 401

    def test_with_invalid_token_gets_401(
        self, client: TestClient
    ) -> None:
        resp = client.get(
            "/admin/health",
            headers={"Authorization": "Bearer invalidtoken"},
        )
        assert resp.status_code == 401


def _get_user_id(db_session: Session, username: str) -> int:
    result = db_session.execute(
        text("SELECT id FROM users WHERE username = :name"),
        {"name": username},
    )
    user_id: int = result.scalar_one()
    return user_id
