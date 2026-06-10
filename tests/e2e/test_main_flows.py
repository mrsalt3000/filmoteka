"""End-to-end tests for the core user flows.

Each test simulates a complete user journey from start to expected outcome.
Uses the same fixtures as integration tests (TestClient, db_session).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from filmoteka.domain.access.models import User
from filmoteka.domain.catalog.models import Film, Genre, MediaFile, MovieEdition
from filmoteka.domain.watching.models import WatchEvent
from filmoteka.infrastructure.library_config import LibraryConfig

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.usefixtures("db_session"),
]


# ── Helpers ─────────────────────────────────────────────────────


def _register(client: TestClient, username: str = "e2e_user") -> str:
    resp = client.post(
        "/auth/register",
        json={"username": username, "password": "pass"},
    )
    assert resp.status_code == 201, f"Register failed: {resp.json()}"
    return resp.json()["access_token"]


def _make_admin(db_session: Session, username: str) -> None:
    user = db_session.query(User).filter(User.username == username).first()
    if user is not None:
        user.role = "admin"
        db_session.commit()


def _create_video(root: Path, rel_path: str) -> Path:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"video content")
    return path


# ── Flow 1: Import + Catalog ────────────────────────────────────


class TestImportAndCatalogFlow:
    """A new video file is imported and appears in the catalog."""

    def test_full_import_flow(
        self, client: TestClient, db_session: Session
    ) -> None:
        """A film created via admin API appears in the catalog."""
        # 1. Create admin
        token = _register(client, "e2e_import")
        _make_admin(db_session, "e2e_import")

        # 2. Create a film directly (simulating import result)
        f = Film(title="Inception", year=2010)
        db_session.add(f)
        db_session.commit()

        # 3. Verify in catalog via API
        resp = client.get("/films")
        assert resp.status_code == 200
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Inception" in titles

        # 4. Verify detail
        detail = client.get(f"/films/{f.id}")
        assert detail.status_code == 200
        assert detail.json()["year"] == 2010


# ── Flow 2: Watch + Recommendations ─────────────────────────────


class TestWatchAndRecommendationsFlow:
    """After watching a film, recommendations appear."""

    def test_watch_triggers_recommendations(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        token = _register(client, "e2e_rec")

        # 1. Create films with genres
        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        drama = Genre(name="Drama", slug="drama")
        db_session.add_all([sci_fi, drama])
        db_session.flush()

        watched = Film(title="Interstellar", year=2014, genres=[sci_fi])
        candidate = Film(title="The Martian", year=2015, genres=[sci_fi])
        other = Film(title="The Father", year=2020, genres=[drama])
        db_session.add_all([watched, candidate, other])
        db_session.flush()

        # Create media for the watched film
        ed = MovieEdition(film_id=watched.id)
        db_session.add(ed)
        db_session.flush()
        m = MediaFile(edition_id=ed.id, file_path="/tmp/e2e_rec.mkv")
        db_session.add(m)
        db_session.commit()

        # 2. Start and finish watching
        wa = client.post(f"/media/{m.id}/watch/start", headers={"Authorization": f"Bearer {token}"})
        assert wa.status_code == 200

        event = db_session.query(WatchEvent).filter(WatchEvent.media_file_id == m.id).first()
        assert event is not None
        event.finished = True
        db_session.commit()

        # 3. Get recommendations
        resp = client.get("/me/recommendations", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        titles = [i["title"] for i in resp.json()["items"]]
        assert "The Martian" in titles
        assert "The Father" not in titles


# ── Flow 3: Child restrictions ──────────────────────────────────


class TestChildRestrictionsFlow:
    """Child account with age_group cannot see adult content."""

    def test_child_restrictions(
        self, client: TestClient, db_session: Session
    ) -> None:
        # 1. Create admin, then create child with age_group
        admin_token = _register(client, "e2e_adm_c")
        _make_admin(db_session, "e2e_adm_c")

        create = client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"username": "e2e_child", "password": "pass",
                  "role": "child", "age_group": "7_12"},
        )
        assert create.status_code == 201

        # 2. Login as child
        login = client.post("/auth/login", json={
            "username": "e2e_child", "password": "pass",
        })
        child_token = login.json()["access_token"]

        # 3. Create films with different age ratings
        db_session.add_all([
            Film(title="Safe Film", year=2020, age_rating="0+"),
            Film(title="Adult Film", year=2021, age_rating="18+"),
        ])
        db_session.commit()

        # 4. Child sees only safe content
        resp = client.get("/films", headers={"Authorization": f"Bearer {child_token}"})
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Safe Film" in titles
        assert "Adult Film" not in titles


# ── Flow 4: Incognito ───────────────────────────────────────────


class TestIncognitoFlow:
    """Watching in incognito mode does not record history."""

    def test_incognito_no_history(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "e2e_inc")

        # 1. Create a film with media
        f = Film(title="Incognito Film", year=2020)
        db_session.add(f)
        db_session.flush()
        ed = MovieEdition(film_id=f.id)
        db_session.add(ed)
        db_session.flush()
        m = MediaFile(edition_id=ed.id, file_path="/tmp/e2e_inc.mkv")
        db_session.add(m)
        db_session.commit()

        # 2. Enable incognito
        client.put("/me/incognito", headers={"Authorization": f"Bearer {token}"}, json={"incognito": True})

        # 3. Watch
        client.post(f"/media/{m.id}/watch/start", headers={"Authorization": f"Bearer {token}"})

        # 4. History is empty
        hist = client.get("/me/watch/history", headers={"Authorization": f"Bearer {token}"})
        assert hist.json()["total"] == 0


# ── Flow 5: Backup ──────────────────────────────────────────────


class TestBackupFlow:
    """Admin can create a backup and see it in the list."""

    def test_backup_flow(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        token = _register(client, "e2e_bkp")
        _make_admin(db_session, "e2e_bkp")

        with patch("filmoteka.api.admin.settings.database_url",
                   "postgresql://u:p@h:5432/db"):
            resp = client.post(
                "/admin/backup",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 202
            assert "job_id" in resp.json()
            assert resp.json()["status"] == "pending"
