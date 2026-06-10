"""Integration tests for admin-only endpoints and role enforcement."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from filmoteka.api.dependencies import get_library_config
from filmoteka.app import create_app
from filmoteka.domain.catalog.models import Film, MediaFile, MovieEdition
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

    def test_child_user_gets_403(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Child user cannot access admin endpoints."""
        token = _create_user(client, "child_admin_test", "pass")
        user_id = _get_user_id(db_session, "child_admin_test")
        db_session.execute(
            text("UPDATE users SET role = 'child' WHERE id = :uid"),
            {"uid": user_id},
        )
        db_session.commit()

        resp = client.get(
            "/admin/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

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
        """POST triggers a background scan and returns 202 with job_id."""
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
        assert body["status"] == "pending"
        assert "job_id" in body

    def test_admin_can_poll_job(
        self, client: TestClient, db_session: Session
    ) -> None:
        """GET /admin/jobs/{id} returns job state."""
        token = _create_admin_token(client, db_session, "import_admin2")

        # Create a job directly in the test DB
        from filmoteka.domain.tasks.models import BackgroundJob
        job = BackgroundJob(type="test", status="pending")
        db_session.add(job)
        db_session.commit()

        resp = client.get(
            f"/admin/jobs/{job.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == job.id
        assert body["status"] == "pending"

        # Non-existent job
        resp = client.get(
            "/admin/jobs/999999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_list_jobs(
        self, client: TestClient, db_session: Session
    ) -> None:
        """GET /admin/jobs returns a paginated list of jobs."""
        token = _create_admin_token(client, db_session, "admin_listjobs")

        from filmoteka.domain.tasks.models import BackgroundJob
        for i in range(3):
            db_session.add(BackgroundJob(type=f"test_{i}", status="completed"))
        db_session.commit()

        resp = client.get(
            "/admin/jobs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 3
        assert len(body["items"]) >= 3

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
# Admin create user
# ---------------------------------------------------------------------------


class TestAdminCreateUser:
    """POST /admin/users — create user with role."""

    def test_without_token_gets_401(
        self, client: TestClient, db_session: Session
    ) -> None:
        resp = client.post(
            "/admin/users",
            json={"username": "newbie", "password": "pass", "role": "user"},
        )
        assert resp.status_code == 401

    def test_regular_user_gets_403(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _create_user(client, "regular_joe", "pass")
        resp = client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": "newbie", "password": "pass", "role": "user"},
        )
        assert resp.status_code == 403

    def test_create_user(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _create_admin_token(client, db_session, "admin_cu")
        resp = client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": "new_user", "password": "secret", "role": "user"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["username"] == "new_user"
        assert body["role"] == "user"
        assert body["is_active"] is True

    def test_create_child(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _create_admin_token(client, db_session, "admin_cc")
        resp = client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": "kid", "password": "pass", "role": "child"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["username"] == "kid"
        assert body["role"] == "child"

    def test_create_user_duplicate(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _create_admin_token(client, db_session, "admin_dup")
        # First creation
        client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": "dup_user", "password": "pass", "role": "user"},
        )
        # Duplicate
        resp = client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": "dup_user", "password": "pass", "role": "user"},
        )
        assert resp.status_code == 409

    def test_create_user_invalid_role(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _create_admin_token(client, db_session, "admin_badrole")
        resp = client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": "bad", "password": "pass", "role": "superadmin"},
        )
        assert resp.status_code == 422

    def test_create_child_with_age_group(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _create_admin_token(client, db_session, "admin_cag")
        resp = client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "username": "kid_with_age",
                "password": "pass",
                "role": "child",
                "age_group": "7_12",
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["username"] == "kid_with_age"
        assert body["role"] == "child"
        assert body["age_group"] == "7_12"

    def test_create_user_invalid_age_group(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _create_admin_token(client, db_session, "admin_badag")
        resp = client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "username": "bad_age",
                "password": "pass",
                "role": "child",
                "age_group": "99_99",
            },
        )
        assert resp.status_code == 422

    def test_update_user_age_group(
        self, client: TestClient, db_session: Session
    ) -> None:
        """PUT /admin/users/{id} sets age_group."""
        admin_token = _create_admin_token(client, db_session, "admin_upd")

        # Create a child user first
        create_resp = client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"username": "updatable_kid", "password": "pass", "role": "child"},
        )
        assert create_resp.status_code == 201
        user_id = create_resp.json()["id"]

        # Update age_group
        resp = client.put(
            f"/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"age_group": "13_17"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["age_group"] == "13_17"

    def test_update_user_nonexistent(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _create_admin_token(client, db_session, "admin_updne")
        resp = client.put(
            "/admin/users/999999",
            headers={"Authorization": f"Bearer {token}"},
            json={"age_group": "0_6"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Poster management
# ---------------------------------------------------------------------------


class TestAdminPosters:
    """POST /admin/posters/fill-missing and /refresh-all."""

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

    @patch.object(settings, "omdb_api_key", None)
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
        assert "OMDB_API_KEY" in str(body.get("error", ""))

    @patch.object(settings, "omdb_api_key", None)
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
        assert "OMDB_API_KEY" in str(body.get("error", ""))

    @patch.object(settings, "omdb_api_key", "test_key")
    def test_fill_missing_updates_only_none(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Fill missing only updates films without poster_url."""
        _create_admin_token(client, db_session, "admin_fill")

        # Create two films: one with poster, one without
        film_with = Film(
            title="Has Poster", year=2020,
            poster_url="http://old/poster.jpg", poster_source="old",
        )
        film_without = Film(title="No Poster", year=2021)
        db_session.add_all([film_with, film_without])
        db_session.commit()
        id_with, id_without = film_with.id, film_without.id

        with patch("filmoteka.api.admin.omdb_search_poster") as mock_search:
            mock_search.return_value = ("http://new/poster.jpg", "omdb")
            # Call the job function directly with the test DB
            from filmoteka.api.admin import _run_fill_missing
            result = _run_fill_missing(db=db_session)

        assert result is not None
        assert result["total"] == 1
        assert result["updated"] == 1

        # Verify
        w = db_session.query(Film).filter(Film.id == id_with).first()
        wo = db_session.query(Film).filter(Film.id == id_without).first()
        assert w is not None and wo is not None
        assert w.poster_url == "http://old/poster.jpg"
        assert w.poster_source == "old"
        assert wo.poster_url == "http://new/poster.jpg"
        assert wo.poster_source == "omdb"

    @patch.object(settings, "omdb_api_key", "test_key")
    def test_refresh_all_updates_all(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Refresh all updates all films regardless of existing poster."""
        _create_admin_token(client, db_session, "admin_refr")

        film_a = Film(
            title="Film A", year=2020,
            poster_url="http://old/a.jpg", poster_source="old",
        )
        film_b = Film(
            title="Film B", year=2021,
            poster_url="http://old/b.jpg", poster_source="old",
        )
        db_session.add_all([film_a, film_b])
        db_session.commit()
        id_a, id_b = film_a.id, film_b.id

        with patch("filmoteka.api.admin.omdb_search_poster") as mock_search:
            mock_search.return_value = ("http://new/poster.jpg", "omdb")
            from filmoteka.api.admin import _run_refresh_all
            result = _run_refresh_all(db=db_session)

        assert result is not None
        assert result["total"] == 2
        assert result["updated"] == 2

        # Verify
        a = db_session.query(Film).filter(Film.id == id_a).first()
        b = db_session.query(Film).filter(Film.id == id_b).first()
        assert a is not None and b is not None
        assert a.poster_url == "http://new/poster.jpg"
        assert b.poster_url == "http://new/poster.jpg"


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


class TestAdminMediaReindex:
    """POST /admin/media/reindex — fix broken media file paths."""

    def test_without_token_gets_401(self, client: TestClient) -> None:
        resp = client.post("/admin/media/reindex")
        assert resp.status_code == 401

    def test_regular_user_gets_403(self, client: TestClient) -> None:
        token = _create_user(client, "regular_reindex", "pass")
        resp = client.post(
            "/admin/media/reindex",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_reindex_fixes_broken_path(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        """MediaFile with a non-existent path gets fixed when the file
        exists under the library root."""
        _create_admin_token(client, db_session, "admin_reindex1")

        test_session = sessionmaker(bind=create_engine(TEST_DATABASE_URL))

        try:
            video = tmp_path / "library" / "Action" / "movie.mp4"
            video.parent.mkdir(parents=True)
            video.write_bytes(b"real content")

            # Insert test data via the test_session
            test_db = test_session()
            film = Film(title="Broken Path", year=2020)
            test_db.add(film)
            test_db.flush()
            edition = MovieEdition(film_id=film.id)
            test_db.add(edition)
            test_db.flush()
            media = MediaFile(
                edition_id=edition.id,
                file_path="/old/media/library/Action/movie.mp4",
                file_size=100,
            )
            test_db.add(media)
            test_db.commit()
            media_id = media.id

            config = LibraryConfig.model_validate({
                "paths": {
                    "downloads_root": str(tmp_path),
                    "target_root": str(tmp_path / "library"),
                },
                "import": {"extensions": [".mp4"], "max_file_size_gb": 50},
                "organization": "by_year",
            })
            client.app.dependency_overrides[get_library_config] = lambda: config  # type: ignore[attr-defined]

            from filmoteka.api.admin import _run_reindex
            result = _run_reindex(config, db=db_session)

            assert result is not None
            assert result["total"] == 1
            assert result["fixed"] == 1
            assert result["skipped"] == 0

            fixed = db_session.query(MediaFile).filter(MediaFile.id == media_id).first()
            assert fixed is not None
            assert fixed.file_path == str(video)
        finally:
            client.app.dependency_overrides.pop(get_library_config, None)  # type: ignore[attr-defined]

    def test_reindex_skips_valid_paths(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        """MediaFile with a valid path is skipped (not counted as fixed)."""
        _create_admin_token(client, db_session, "admin_reindex2")

        try:
            video = tmp_path / "valid.mp4"
            video.write_bytes(b"content")

            film = Film(title="Valid Path", year=2020)
            db_session.add(film)
            db_session.flush()
            edition = MovieEdition(film_id=film.id)
            db_session.add(edition)
            db_session.flush()
            media = MediaFile(
                edition_id=edition.id,
                file_path=str(video),
                file_size=100,
            )
            db_session.add(media)
            db_session.commit()

            config = LibraryConfig.model_validate({
                "paths": {
                    "downloads_root": str(tmp_path),
                    "target_root": str(tmp_path),
                },
                "import": {"extensions": [".mp4"], "max_file_size_gb": 50},
                "organization": "by_year",
            })
            client.app.dependency_overrides[get_library_config] = lambda: config  # type: ignore[attr-defined]

            from filmoteka.api.admin import _run_reindex
            result = _run_reindex(config, db=db_session)

            assert result is not None
            assert result["total"] >= 1
            assert result["fixed"] == 0
            assert result["skipped"] >= 1
        finally:
            client.app.dependency_overrides.pop(get_library_config, None)  # type: ignore[attr-defined]


# ── Background job infrastructure ────────────────────────────────


class TestBackgroundJobs:
    """BackgroundJob lifecycle and list endpoint."""

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_job_lifecycle(
        self, client: TestClient, db_session: Session
    ) -> None:
        """pending → running → completed lifecycle."""
        from filmoteka.domain.tasks.models import BackgroundJob
        job = BackgroundJob(type="test_lifecycle", status="pending")
        db_session.add(job)
        db_session.commit()
        assert job.status == "pending"

        job.status = "running"
        db_session.commit()
        assert job.status == "running"

        job.status = "completed"
        job.result = {"ok": True}
        db_session.commit()

        token = _create_admin_token(client, db_session, "bg_lifecycle")
        resp = client.get(
            f"/admin/jobs/{job.id}",
            headers=self._auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["result"] == {"ok": True}

    def test_job_failure(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Job error is persisted and visible via API."""
        from filmoteka.domain.tasks.models import BackgroundJob
        job = BackgroundJob(type="test_fail", status="failed", error="Something broke")
        db_session.add(job)
        db_session.commit()

        token = _create_admin_token(client, db_session, "bg_fail")
        resp = client.get(
            f"/admin/jobs/{job.id}",
            headers=self._auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert "Something broke" in body["error"]

    def test_job_result_stored(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Job result with nested dict is stored and returned."""
        from filmoteka.domain.tasks.models import BackgroundJob
        result = {"total": 10, "updated": 5, "errors": ["err1"]}
        job = BackgroundJob(type="test_result", status="completed", result=result)
        db_session.add(job)
        db_session.commit()

        token = _create_admin_token(client, db_session, "bg_result")
        resp = client.get(
            f"/admin/jobs/{job.id}",
            headers=self._auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["result"]["total"] == 10
        assert body["result"]["errors"] == ["err1"]

    def test_list_jobs_pagination(
        self, client: TestClient, db_session: Session
    ) -> None:
        """GET /admin/jobs respects skip and limit."""
        token = _create_admin_token(client, db_session, "bg_paginate")

        resp = client.get(
            "/admin/jobs?skip=0&limit=2",
            headers=self._auth(token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) <= 2

    def test_get_job_not_found(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Non-existent job ID returns 404."""
        token = _create_admin_token(client, db_session, "bg_notfound")
        resp = client.get(
            "/admin/jobs/999999",
            headers=self._auth(token),
        )
        assert resp.status_code == 404
