"""Integration tests for authentication endpoints."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
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


class TestRegister:
    """POST /auth/register"""

    def test_register_success(self, client: TestClient) -> None:
        resp = client.post(
            "/auth/register",
            json={"username": "alice", "password": "secret123"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    def test_register_duplicate_username(self, client: TestClient) -> None:
        client.post(
            "/auth/register",
            json={"username": "bob", "password": "secret123"},
        )
        resp = client.post(
            "/auth/register",
            json={"username": "bob", "password": "other456"},
        )
        assert resp.status_code == 409
        assert "already taken" in resp.json()["detail"]

    def test_register_username_too_short(self, client: TestClient) -> None:
        resp = client.post(
            "/auth/register",
            json={"username": "a", "password": "secret123"},
        )
        assert resp.status_code == 422

    def test_register_password_too_short(self, client: TestClient) -> None:
        resp = client.post(
            "/auth/register",
            json={"username": "testuser", "password": "ab"},
        )
        assert resp.status_code == 422


class TestLogin:
    """POST /auth/login"""

    def test_login_success(self, client: TestClient) -> None:
        client.post(
            "/auth/register",
            json={"username": "carol", "password": "mypassword"},
        )
        resp = client.post(
            "/auth/login",
            json={"username": "carol", "password": "mypassword"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body

    def test_login_wrong_password(self, client: TestClient) -> None:
        client.post(
            "/auth/register",
            json={"username": "dave", "password": "correctpw"},
        )
        resp = client.post(
            "/auth/login",
            json={"username": "dave", "password": "wrongpw"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_user(self, client: TestClient) -> None:
        resp = client.post(
            "/auth/login",
            json={"username": "nobody", "password": "irrelevant"},
        )
        assert resp.status_code == 401


class TestMe:
    """GET /auth/me"""

    def test_me_with_valid_token(self, client: TestClient) -> None:
        resp = client.post(
            "/auth/register",
            json={"username": "eve", "password": "p4ssword"},
        )
        token = resp.json()["access_token"]

        resp = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["username"] == "eve"
        assert body["is_active"] is True
        assert "id" in body

    def test_me_without_token(self, client: TestClient) -> None:
        resp = client.get("/auth/me")
        assert resp.status_code == 401

    def test_me_with_invalid_token(self, client: TestClient) -> None:
        resp = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalidtoken"},
        )
        assert resp.status_code == 401
