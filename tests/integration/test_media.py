"""Integration tests for media streaming endpoints."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from filmoteka.app import create_app
from filmoteka.domain.catalog.models import Film, MediaFile, MovieEdition
from filmoteka.domain.watching.models import WatchEvent
from filmoteka.infrastructure.database import get_db

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient with DB dependency overridden to the integration test DB."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c


def _auth_token(client: TestClient) -> str:
    """Register a test user and return a Bearer token."""
    return _register_user(client, "watchtest", "secret123")


class TestStreamMedia:
    """GET /media/{id}/stream"""

    def _create_media(self, db_session: Session, file_path: str) -> MediaFile:
        film = Film(title="Test", year=2020)
        db_session.add(film)
        db_session.flush()

        edition = MovieEdition(film_id=film.id)
        db_session.add(edition)
        db_session.flush()

        media = MediaFile(
            edition_id=edition.id,
            file_path=file_path,
            file_size=100,
            duration_secs=10.0,
            width=1920,
            height=1080,
            codec="h264",
        )
        db_session.add(media)
        db_session.commit()
        return media

    def test_not_found(self, client: TestClient) -> None:
        resp = client.get("/media/99999/stream")
        assert resp.status_code == 404

    def test_file_not_on_disk(
        self, client: TestClient, db_session: Session
    ) -> None:
        media = self._create_media(db_session, "/nonexistent/file.mkv")
        resp = client.get(f"/media/{media.id}/stream")
        assert resp.status_code == 404

    def test_stream_success(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        video = tmp_path / "movie.mp4"
        video.write_bytes(b"fake video content")

        media = self._create_media(db_session, str(video))
        resp = client.get(f"/media/{media.id}/stream")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "video/mp4"
        assert resp.content == b"fake video content"

    def test_stream_with_range(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        video = tmp_path / "movie.mp4"
        video.write_bytes(b"0123456789abcdef")

        media = self._create_media(db_session, str(video))
        resp = client.get(
            f"/media/{media.id}/stream",
            headers={"Range": "bytes=5-9"},
        )
        # FastAPI FileResponse returns 206 for valid Range requests
        assert resp.status_code == 206
        assert resp.content == b"56789"


class TestWatchStart:
    """POST /media/{id}/watch/start"""

    def _create_media(self, db_session: Session) -> MediaFile:
        film = Film(title="Watch Test", year=2020)
        db_session.add(film)
        db_session.flush()

        edition = MovieEdition(film_id=film.id)
        db_session.add(edition)
        db_session.flush()

        media = MediaFile(
            edition_id=edition.id,
            file_path="/tmp/test.mkv",
            file_size=100,
        )
        db_session.add(media)
        db_session.commit()
        return media

    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.post("/media/1/watch/start")
        assert resp.status_code == 401

    def test_not_found(self, client: TestClient) -> None:
        token = _auth_token(client)
        resp = client.post(
            "/media/99999/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_start_success(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _auth_token(client)
        media = self._create_media(db_session)

        resp = client.post(
            f"/media/{media.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["media_file_id"] == media.id
        assert body["last_position"] == 0.0
        assert body["finished"] is False
        assert "watch_event_id" in body
        assert "started_at" in body

    def test_resume_returns_existing(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _auth_token(client)
        media = self._create_media(db_session)

        # First start
        resp1 = client.post(
            f"/media/{media.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp1.status_code == 200
        event_id_1 = resp1.json()["watch_event_id"]

        # Second start — should return the same event (resume)
        resp2 = client.post(
            f"/media/{media.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["watch_event_id"] == event_id_1


class TestUpdateProgress:
    """PATCH /media/{id}/watch/{watch_event_id}/progress"""

    def test_requires_auth(
        self, client: TestClient, db_session: Session
    ) -> None:
        media = self._create_media(db_session)
        event = self._start_watch(client, media)

        resp = client.patch(
            f"/media/{media.id}/watch/{event}/progress",
            json={"position": 100.5},
        )
        assert resp.status_code == 401

    def test_not_found(self, client: TestClient) -> None:
        token = _auth_token(client)
        resp = client.patch(
            "/media/1/watch/99999/progress",
            json={"position": 100.5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    def test_forbidden_another_user(
        self, client: TestClient, db_session: Session
    ) -> None:
        # Create an event as user A
        media = self._create_media(db_session)
        token_a = _auth_token(client)
        resp = client.post(
            f"/media/{media.id}/watch/start",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 200
        event_id = resp.json()["watch_event_id"]

        # Try to update it as user B
        client2 = client  # Reuse the same TestClient but register a new user
        token_b = _register_user(client, "other", "pass456")

        resp = client2.patch(
            f"/media/{media.id}/watch/{event_id}/progress",
            json={"position": 50.0},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.status_code == 403

    def test_update_success(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _auth_token(client)
        media = self._create_media(db_session)

        # Start watch
        resp_start = client.post(
            f"/media/{media.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        event_id = resp_start.json()["watch_event_id"]

        # Update position
        resp = client.patch(
            f"/media/{media.id}/watch/{event_id}/progress",
            json={"position": 123.45},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Verify the position was persisted
        watch = db_session.get(WatchEvent, event_id)
        assert watch is not None
        assert watch.last_position == 123.45

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create_media(db_session: Session) -> MediaFile:
        film = Film(title="Progress Test", year=2020)
        db_session.add(film)
        db_session.flush()
        edition = MovieEdition(film_id=film.id)
        db_session.add(edition)
        db_session.flush()
        media = MediaFile(edition_id=edition.id, file_path="/tmp/p.mkv", file_size=100)
        db_session.add(media)
        db_session.commit()
        return media

    @staticmethod
    def _start_watch(client: TestClient, media: MediaFile) -> int:
        token = _auth_token(client)
        resp = client.post(
            f"/media/{media.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        event_id: int = resp.json()["watch_event_id"]
        return event_id


def _register_user(client: TestClient, username: str, password: str) -> str:
    """Register a user and return token."""
    resp = client.post(
        "/auth/register",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 201
    token: str = resp.json()["access_token"]
    return token
