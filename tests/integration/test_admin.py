"""Integration tests for admin-only endpoints and role enforcement."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from filmoteka.api.dependencies import get_library_config
from filmoteka.app import create_app
from filmoteka.infrastructure.database import get_db
from filmoteka.infrastructure.library_config import LibraryConfig

pytestmark = pytest.mark.integration


def _make_config(
    downloads_root: Path,
    target_root: str | None = None,
) -> LibraryConfig:
    return LibraryConfig.model_validate({
        "paths": {
            "downloads_root": str(downloads_root),
            "target_root": target_root or "/media/library",
        },
        "import": {"extensions": [".mp4", ".mkv"], "max_file_size_gb": 50},
        "organization": "by_year",
    })


@pytest.fixture
def client(db_session: Session, tmp_path: Path) -> Generator[TestClient, None, None]:
    """TestClient with DB + library_config dependencies overridden."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_library_config] = lambda: _make_config(tmp_path)
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


class TestAdminImportScan:
    """POST /admin/import/scan — role enforcement + pipeline trigger."""

    def test_admin_can_trigger_scan(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        """Create an admin user and a test video, then trigger import."""
        token = _create_user(client, "import_admin", "pass")
        user_id = _get_user_id(db_session, "import_admin")
        db_session.execute(
            text("UPDATE users SET role = 'admin' WHERE id = :uid"),
            {"uid": user_id},
        )
        db_session.commit()

        # Place a test video in the downloads dir
        video = tmp_path / "The.Matrix.1999.1080p.mkv"
        video.write_text("fake video content")

        resp = client.post(
            "/admin/import/scan",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["files_found"] == 1
        assert body["files_probed"] == 0  # no ffprobe — fake file
        assert body["films_created"] == 0  # no probe → no layout → no bridge
        assert body["errors"] == []

    def test_regular_user_gets_403(
        self, client: TestClient
    ) -> None:
        token = _create_user(client, "regular_scan", "pass")
        resp = client.post(
            "/admin/import/scan",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_without_token_gets_401(
        self, client: TestClient
    ) -> None:
        resp = client.post("/admin/import/scan")
        assert resp.status_code == 401


def _get_user_id(db_session: Session, username: str) -> int:
    result = db_session.execute(
        text("SELECT id FROM users WHERE username = :name"),
        {"name": username},
    )
    user_id: int = result.scalar_one()
    return user_id
