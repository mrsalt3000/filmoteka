"""Integration tests for admin-only endpoints and role enforcement."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from filmoteka.api.dependencies import get_library_config
from filmoteka.app import create_app
from filmoteka.domain.catalog.models import Film
from filmoteka.infrastructure.database import get_db
from filmoteka.infrastructure.library_config import LibraryConfig
from filmoteka.infrastructure.settings import settings

from .conftest import TEST_DATABASE_URL

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
    """POST /admin/import/scan — background scan, role enforcement."""

    def test_admin_can_trigger_scan(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        """POST triggers a background scan and returns 202."""
        token = _create_user(client, "import_admin", "pass")
        user_id = _get_user_id(db_session, "import_admin")
        db_session.execute(
            text("UPDATE users SET role = 'admin' WHERE id = :uid"),
            {"uid": user_id},
        )
        db_session.commit()

        resp = client.post(
            "/admin/import/scan",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "running"
        assert body["task_id"] == "import-scan"

    def test_admin_can_poll_status(
        self, client: TestClient, db_session: Session
    ) -> None:
        """GET /admin/import/status returns task state."""
        token = _create_user(client, "import_admin2", "pass")
        user_id = _get_user_id(db_session, "import_admin2")
        db_session.execute(
            text("UPDATE users SET role = 'admin' WHERE id = :uid"),
            {"uid": user_id},
        )
        db_session.commit()

        resp = client.get(
            "/admin/import/status",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["task_id"] == "import-scan"
        assert body["status"] in ("idle", "running", "completed", "failed")

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


def _create_admin_token(
    client: TestClient, db_session: Session, username: str, password: str = "pass"
) -> str:
    """Register a user and promote to admin, return the token."""
    token = _create_user(client, username, password)
    user_id = _get_user_id(db_session, username)
    db_session.execute(
        text("UPDATE users SET role = 'admin' WHERE id = :uid"),
        {"uid": user_id},
    )
    db_session.commit()
    return token


# ---------------------------------------------------------------------------
# Poster management
# ---------------------------------------------------------------------------


class TestAdminPosters:
    """POST /admin/posters/fill-missing and /refresh-all."""

    def _poll_status(
        self, client: TestClient, token: str, max_attempts: int = 30
    ) -> Any:
        """Poll poster status until completed or failed."""
        import time
        for _ in range(max_attempts):
            time.sleep(0.1)
            resp = client.get(
                "/admin/posters/status",
                headers={"Authorization": f"Bearer {token}"},
            )
            body: dict[str, object] = resp.json()
            status = body.get("status")
            if status in ("completed", "failed", "idle", "error"):
                return body
        raise AssertionError("Poster operation did not complete in time")

    def test_without_token_gets_401_fill(self, client: TestClient) -> None:
        resp = client.post("/admin/posters/fill-missing")
        assert resp.status_code == 401

    def test_without_token_gets_401_refresh(self, client: TestClient) -> None:
        resp = client.post("/admin/posters/refresh-all")
        assert resp.status_code == 401

    def test_regular_user_gets_403_fill(self, client: TestClient) -> None:
        token = _create_user(client, "regular_pf", "pass")
        resp = client.post(
            "/admin/posters/fill-missing",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_regular_user_gets_403_refresh(self, client: TestClient) -> None:
        token = _create_user(client, "regular_pr", "pass")
        resp = client.post(
            "/admin/posters/refresh-all",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    @patch.object(settings, "tmdb_api_key", None)
    def test_fill_missing_no_api_key(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _create_admin_token(client, db_session, "admin_nokey_f")
        resp = client.post(
            "/admin/posters/fill-missing",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = resp.json()
        assert body["status"] == "error"
        assert "TMDB_API_KEY" in str(body.get("error", ""))

    @patch.object(settings, "tmdb_api_key", None)
    def test_refresh_all_no_api_key(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _create_admin_token(client, db_session, "admin_nokey_r")
        resp = client.post(
            "/admin/posters/refresh-all",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = resp.json()
        assert body["status"] == "error"
        assert "TMDB_API_KEY" in str(body.get("error", ""))

    @patch.object(settings, "tmdb_api_key", "test_key")
    def test_fill_missing_updates_only_none(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Fill missing only updates films without poster_url."""
        token = _create_admin_token(client, db_session, "admin_fill")

        # Use a dedicated test session maker for the background thread
        test_session = sessionmaker(bind=create_engine(TEST_DATABASE_URL))
        test_db = test_session()
        id_with = id_without = 0

        try:
            # Create two films: one with poster, one without
            film_with = Film(
                title="Has Poster", year=2020,
                poster_url="http://old/poster.jpg", poster_source="old",
            )
            film_without = Film(title="No Poster", year=2021)
            test_db.add_all([film_with, film_without])
            test_db.commit()
            id_with, id_without = film_with.id, film_without.id

            with (
                patch("filmoteka.api.admin.tmdb_search_poster") as mock_search,
                patch("filmoteka.api.admin.SessionLocal", test_session),
            ):
                mock_search.return_value = ("http://new/poster.jpg", "tmdb")

                resp = client.post(
                    "/admin/posters/fill-missing",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 202

                result = self._poll_status(client, token)
                assert result["status"] == "completed"
                report = result["report"]
                assert report is not None
                assert report["total"] == 1
                assert report["updated"] == 1

            # Verify via fresh query (test_db session was closed by thread)
            check = test_session()
            try:
                w = check.query(Film).filter(Film.id == id_with).first()
                wo = check.query(Film).filter(Film.id == id_without).first()
                assert w is not None and wo is not None
                assert w.poster_url == "http://old/poster.jpg"
                assert w.poster_source == "old"
                assert wo.poster_url == "http://new/poster.jpg"
                assert wo.poster_source == "tmdb"
            finally:
                check.close()
        finally:
            cleanup = test_session()
            cleanup.query(Film).filter(
                Film.id.in_([id_with, id_without])
            ).delete(synchronize_session=False)
            cleanup.commit()
            cleanup.close()
            test_db.close()

    @patch.object(settings, "tmdb_api_key", "test_key")
    def test_refresh_all_updates_all(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Refresh all updates all films regardless of existing poster."""
        token = _create_admin_token(client, db_session, "admin_refr")

        # Use a dedicated test session maker for the background thread
        test_session = sessionmaker(bind=create_engine(TEST_DATABASE_URL))
        test_db = test_session()
        id_a = id_b = 0

        try:
            # Create two films, both with posters
            film_a = Film(
                title="Film A", year=2020,
                poster_url="http://old/a.jpg", poster_source="old",
            )
            film_b = Film(
                title="Film B", year=2021,
                poster_url="http://old/b.jpg", poster_source="old",
            )
            test_db.add_all([film_a, film_b])
            test_db.commit()
            id_a, id_b = film_a.id, film_b.id

            with (
                patch("filmoteka.api.admin.tmdb_search_poster") as mock_search,
                patch("filmoteka.api.admin.SessionLocal", test_session),
            ):
                mock_search.return_value = ("http://new/poster.jpg", "tmdb")

                resp = client.post(
                    "/admin/posters/refresh-all",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 202

                result = self._poll_status(client, token)
                assert result["status"] == "completed"
                report = result["report"]
                assert report is not None
                assert report["total"] == 2
                assert report["updated"] == 2

            # Verify via fresh query
            check = test_session()
            try:
                a = check.query(Film).filter(Film.id == id_a).first()
                b = check.query(Film).filter(Film.id == id_b).first()
                assert a is not None and b is not None
                assert a.poster_url == "http://new/poster.jpg"
                assert b.poster_url == "http://new/poster.jpg"
            finally:
                check.close()
        finally:
            # Clean up test data via a fresh session
            cleanup = test_session()
            cleanup.query(Film).filter(Film.id.in_([id_a, id_b])).delete(
                synchronize_session=False
            )
            cleanup.commit()
            cleanup.close()
            test_db.close()


class TestAdminFilmEdit:
    """PUT /admin/films/{film_id} — film card editing."""

    def _create_film(
        self, db_session: Session, title: str = "Original Title",
        year: int = 2020, description: str | None = "Original desc.",
        needs_review: bool = False,
    ) -> Film:
        film = Film(
            title=title, year=year, description=description,
            needs_review=needs_review,
        )
        db_session.add(film)
        db_session.commit()
        db_session.refresh(film)
        return film

    def test_without_token_gets_401(
        self, client: TestClient, db_session: Session
    ) -> None:
        film = self._create_film(db_session)
        resp = client.put(f"/admin/films/{film.id}", json={"title": "New"})
        assert resp.status_code == 401

    def test_regular_user_gets_403(
        self, client: TestClient, db_session: Session
    ) -> None:
        film = self._create_film(db_session)
        token = _create_user(client, "regular_edit", "pass")
        resp = client.put(
            f"/admin/films/{film.id}",
            json={"title": "New"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_edit_nonexistent_film_returns_404(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _create_admin_token(client, db_session, "admin_edit_404")
        resp = client.put(
            "/admin/films/99999",
            json={"title": "Nope"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_admin_can_edit_title(
        self, client: TestClient, db_session: Session
    ) -> None:
        film = self._create_film(db_session)
        token = _create_admin_token(client, db_session, "admin_edit_t")
        resp = client.put(
            f"/admin/films/{film.id}",
            json={"title": "New Title"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "New Title"
        assert body["year"] == 2020
        assert body["description"] == "Original desc."

    def test_admin_can_edit_year(
        self, client: TestClient, db_session: Session
    ) -> None:
        film = self._create_film(db_session)
        token = _create_admin_token(client, db_session, "admin_edit_y")
        resp = client.put(
            f"/admin/films/{film.id}",
            json={"year": 1999},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Original Title"
        assert body["year"] == 1999

    def test_admin_can_edit_description(
        self, client: TestClient, db_session: Session
    ) -> None:
        film = self._create_film(db_session)
        token = _create_admin_token(client, db_session, "admin_edit_d")
        resp = client.put(
            f"/admin/films/{film.id}",
            json={"description": "New desc."},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["description"] == "New desc."

    def test_admin_can_edit_all_fields(
        self, client: TestClient, db_session: Session
    ) -> None:
        film = self._create_film(db_session)
        token = _create_admin_token(client, db_session, "admin_edit_all")
        resp = client.put(
            f"/admin/films/{film.id}",
            json={"title": "A", "year": 2001, "description": "B"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "A"
        assert body["year"] == 2001
        assert body["description"] == "B"

    def test_edit_clears_needs_review(
        self, client: TestClient, db_session: Session
    ) -> None:
        film = self._create_film(db_session, needs_review=True)
        assert film.needs_review is True
        token = _create_admin_token(client, db_session, "admin_edit_nr")
        resp = client.put(
            f"/admin/films/{film.id}",
            json={"title": "Fixed"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["needs_review"] is False
        assert body["title"] == "Fixed"

    def test_edit_without_changes_preserves_needs_review(
        self, client: TestClient, db_session: Session
    ) -> None:
        film = self._create_film(db_session, needs_review=True)
        token = _create_admin_token(client, db_session, "admin_edit_nc")
        resp = client.put(
            f"/admin/films/{film.id}",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # No fields changed → needs_review stays True
        assert body["needs_review"] is True
        assert body["title"] == "Original Title"
