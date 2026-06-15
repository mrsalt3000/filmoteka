"""Integration tests for media streaming endpoints."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from filmoteka.api.dependencies import get_library_config
from filmoteka.app import create_app
from filmoteka.domain.catalog.models import Film, MediaFile, MovieEdition, Series
from filmoteka.domain.watching.models import WatchEvent
from filmoteka.infrastructure.database import get_db
from filmoteka.infrastructure.library_config import LibraryConfig

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

    def test_stream_webm_mime(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        """.webm files get video/webm MIME type."""
        video = tmp_path / "movie.webm"
        video.write_bytes(b"fake webm")
        media = self._create_media(db_session, str(video))

        resp = client.get(f"/media/{media.id}/stream")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "video/webm"

    def test_stream_avi_mime(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        """.avi files get video/x-msvideo MIME type."""
        video = tmp_path / "movie.avi"
        video.write_bytes(b"fake avi")
        media = self._create_media(db_session, str(video))

        resp = client.get(f"/media/{media.id}/stream")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "video/x-msvideo"

    def test_stream_mkv_without_ffmpeg_returns_415(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        """MKV without ffmpeg returns 415."""
        video = tmp_path / "movie.mkv"
        video.write_bytes(b"fake mkv")
        media = self._create_media(db_session, str(video))

        with patch("filmoteka.api.media._ffmpeg_available", return_value=False):
            resp = client.get(f"/media/{media.id}/stream")
        assert resp.status_code == 415
        assert "MKV" in resp.text

    def test_head_mkv_without_ffmpeg_returns_415(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        """HEAD for MKV without ffmpeg also returns 415."""
        video = tmp_path / "movie.mkv"
        video.write_bytes(b"fake mkv")
        media = self._create_media(db_session, str(video))

        with patch("filmoteka.api.media._ffmpeg_available", return_value=False):
            resp = client.head(f"/media/{media.id}/stream")
        assert resp.status_code == 415

    def test_head_mkv_with_ffmpeg_returns_ok(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        """HEAD for MKV with ffmpeg returns 200 and correct MIME."""
        video = tmp_path / "movie.mkv"
        video.write_bytes(b"fake mkv")
        media = self._create_media(db_session, str(video))

        with patch("filmoteka.api.media._ffmpeg_available", return_value=True):
            resp = client.head(f"/media/{media.id}/stream")
        assert resp.status_code == 200
        # MIME is still video/x-matroska for the HEAD check
        assert resp.headers["content-type"] == "video/x-matroska"

    def test_mkv_with_cyrillic_filename_does_not_500(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        """MKV with a non-ASCII filename returns 200 (not 500) when ffmpeg
        is available.  Regression test for a bug where ``path.stem`` was
        embedded directly in the ``Content-Disposition`` header, which
        must be latin-1."""
        video = tmp_path / "Начало.mkv"
        video.write_bytes(b"fake mkv")
        media = self._create_media(db_session, str(video))

        with patch("filmoteka.api.media._ffmpeg_available", return_value=True):
            resp = client.get(f"/media/{media.id}/stream")
        # 200 means the StreamingResponse was constructed successfully;
        # actual body comes from ffmpeg which isn't really running.
        assert resp.status_code == 200
        # Content-Disposition header must be present and valid
        disp = resp.headers.get("content-disposition", "")
        assert "filename*=UTF-8''" in disp
        assert "%D0%9D%D0%B0%D1%87%D0%B0%D0%BB%D0%BE" in disp


class TestStreamMediaAutoFix:
    """Auto-fix: stream endpoint resolves broken paths under library_root."""

    def test_auto_fix_resolves_broken_path(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        """When stored path doesn't resolve but the file exists under
        library_root, the endpoint serves it and updates the DB path."""
        # Create the real file under library_root
        lib_root = tmp_path / "library"
        video = lib_root / "Action" / "movie.mp4"
        video.parent.mkdir(parents=True)
        video.write_bytes(b"real content")

        # MediaFile with a broken (old) path
        film = Film(title="AutoFix", year=2020)
        db_session.add(film)
        db_session.flush()
        edition = MovieEdition(film_id=film.id)
        db_session.add(edition)
        db_session.flush()
        media = MediaFile(
            edition_id=edition.id,
            file_path="/old/library/Action/movie.mp4",
            file_size=100,
        )
        db_session.add(media)
        db_session.commit()
        media_id = media.id

        # Override LibraryConfig to point at our test library root
        config = LibraryConfig.model_validate({
            "paths": {
                "downloads_root": str(tmp_path),
                "target_root": str(lib_root),
            },
            "import": {"extensions": [".mp4"], "max_file_size_gb": 50},
            "organization": "by_year",
        })
        client.app.dependency_overrides[get_library_config] = lambda: config  # type: ignore[attr-defined]

        try:
            resp = client.get(f"/media/{media_id}/stream")
            assert resp.status_code == 200
            assert resp.content == b"real content"

            # Verify the DB path was updated
            db_session.refresh(media)
            assert media.file_path == str(video)
        finally:
            client.app.dependency_overrides.pop(get_library_config, None)  # type: ignore[attr-defined]

    def test_auto_fix_returns_404_when_not_found(
        self, client: TestClient, db_session: Session, tmp_path: Path
    ) -> None:
        """When neither the stored path nor the library root has the file,
        the endpoint still returns 404."""
        lib_root = tmp_path / "library"
        lib_root.mkdir()

        film = Film(title="NoFile", year=2020)
        db_session.add(film)
        db_session.flush()
        edition = MovieEdition(film_id=film.id)
        db_session.add(edition)
        db_session.flush()
        media = MediaFile(
            edition_id=edition.id,
            file_path=str(tmp_path / "nonexistent.mp4"),
            file_size=100,
        )
        db_session.add(media)
        db_session.commit()
        media_id = media.id

        config = LibraryConfig.model_validate({
            "paths": {
                "downloads_root": str(tmp_path),
                "target_root": str(lib_root),
            },
            "import": {"extensions": [".mp4"], "max_file_size_gb": 50},
            "organization": "by_year",
        })
        client.app.dependency_overrides[get_library_config] = lambda: config  # type: ignore[attr-defined]

        try:
            resp = client.get(f"/media/{media_id}/stream")
            assert resp.status_code == 404
        finally:
            client.app.dependency_overrides.pop(get_library_config, None)  # type: ignore[attr-defined]


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


class TestWatchState:
    """GET /media/{id}/watch/state"""

    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/media/1/watch/state")
        assert resp.status_code == 401

    def test_no_state(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register_user(client, "nostate", "pass")
        media = self._create_media(db_session)

        resp = client.get(
            f"/media/{media.id}/watch/state",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_state"] is False

    def test_returns_unfinished_event(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register_user(client, "resume", "pass")
        media = self._create_media(db_session)

        # Start watch
        start_resp = client.post(
            f"/media/{media.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        event_id = start_resp.json()["watch_event_id"]

        # Update position
        client.patch(
            f"/media/{media.id}/watch/{event_id}/progress",
            json={"position": 300.0},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Check state — should return the event with position
        resp = client.get(
            f"/media/{media.id}/watch/state",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_state"] is True
        assert body["watch_event_id"] == event_id
        assert body["last_position"] == 300.0
        assert body["finished"] is False

    def test_media_not_found_returns_false(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register_user(client, "nomedi", "pass")

        resp = client.get(
            "/media/99999/watch/state",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["has_state"] is False

    def test_no_state_when_finished(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register_user(client, "doneuser", "pass")
        media = self._create_media(db_session)

        # Start watch
        start_resp = client.post(
            f"/media/{media.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        event_id = start_resp.json()["watch_event_id"]

        # Mark as finished
        event = db_session.get(WatchEvent, event_id)
        assert event is not None
        event.finished = True
        db_session.commit()

        # State should be empty
        resp = client.get(
            f"/media/{media.id}/watch/state",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = resp.json()
        assert body["has_state"] is False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create_media(db_session: Session) -> MediaFile:
        film = Film(title="State Test", year=2020)
        db_session.add(film)
        db_session.flush()
        edition = MovieEdition(film_id=film.id)
        db_session.add(edition)
        db_session.flush()
        media = MediaFile(edition_id=edition.id, file_path="/tmp/s.mkv", file_size=100)
        db_session.add(media)
        db_session.commit()
        return media


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

    def test_update_position_zero(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _auth_token(client)
        media = self._create_media(db_session)

        resp_start = client.post(
            f"/media/{media.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        event_id = resp_start.json()["watch_event_id"]

        # Set position to 300 first, then reset to 0
        client.patch(
            f"/media/{media.id}/watch/{event_id}/progress",
            json={"position": 300.0},
            headers={"Authorization": f"Bearer {token}"},
        )
        resp = client.patch(
            f"/media/{media.id}/watch/{event_id}/progress",
            json={"position": 0.0},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        watch = db_session.get(WatchEvent, event_id)
        assert watch is not None
        assert watch.last_position == 0.0

    def test_update_negative_position(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _auth_token(client)
        media = self._create_media(db_session)

        resp_start = client.post(
            f"/media/{media.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        event_id = resp_start.json()["watch_event_id"]

        resp = client.patch(
            f"/media/{media.id}/watch/{event_id}/progress",
            json={"position": -5.0},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

        watch = db_session.get(WatchEvent, event_id)
        assert watch is not None
        assert watch.last_position == -5.0

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


class TestWatchStatesByFilm:
    """POST /media/watch/states-by-film"""

    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.post(
            "/media/watch/states-by-film",
            json={"film_ids": [1]},
        )
        assert resp.status_code == 401

    def test_empty_list(self, client: TestClient) -> None:
        token = _register_user(client, "emptyws", "pass")
        resp = client.post(
            "/media/watch/states-by-film",
            json={"film_ids": []},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["states"] == {}

    def test_no_media_no_state(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register_user(client, "nomedws", "pass")
        film = Film(title="No Media", year=2020)
        db_session.add(film)
        db_session.commit()

        resp = client.post(
            "/media/watch/states-by-film",
            json={"film_ids": [film.id]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["states"][str(film.id)]["has_state"] is False

    def test_returns_unfinished_state(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register_user(client, "batchws", "pass")

        # Create film with media
        film = Film(title="Batch Test", year=2020)
        db_session.add(film)
        db_session.flush()
        edition = MovieEdition(film_id=film.id)
        db_session.add(edition)
        db_session.flush()
        media = MediaFile(
            edition_id=edition.id,
            file_path="/tmp/batch.mkv",
            file_size=100,
            duration_secs=7200.0,
        )
        db_session.add(media)
        db_session.commit()

        # Start watch and set some progress
        start = client.post(
            f"/media/{media.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        event_id = start.json()["watch_event_id"]
        client.patch(
            f"/media/{media.id}/watch/{event_id}/progress",
            json={"position": 300.0},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Batch fetch
        resp = client.post(
            "/media/watch/states-by-film",
            json={"film_ids": [film.id]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        state = body["states"][str(film.id)]
        assert state["has_state"] is True
        assert state["last_position"] == 300.0
        assert state["duration_secs"] == 7200.0
        assert state["finished"] is False

    def test_multiple_films_mixed_state(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register_user(client, "mixws", "pass")

        def _make_film(title: str) -> tuple[Film, MediaFile]:
            f = Film(title=title, year=2020)
            db_session.add(f)
            db_session.flush()
            ed = MovieEdition(film_id=f.id)
            db_session.add(ed)
            db_session.flush()
            m = MediaFile(
                edition_id=ed.id,
                file_path=f"/tmp/{title}.mkv",
                file_size=100,
                duration_secs=3600.0,
            )
            db_session.add(m)
            db_session.flush()
            return f, m

        film_a, media_a = _make_film("Watched A")
        film_b, media_b = _make_film("Watched B")
        film_c, _ = _make_film("Unwatched C")
        db_session.commit()

        # Start watch for A and B
        resp_a = client.post(
            f"/media/{media_a.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        event_a = resp_a.json()["watch_event_id"]
        client.patch(
            f"/media/{media_a.id}/watch/{event_a}/progress",
            json={"position": 100.0},
            headers={"Authorization": f"Bearer {token}"},
        )

        resp_b = client.post(
            f"/media/{media_b.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        event_b = resp_b.json()["watch_event_id"]
        client.patch(
            f"/media/{media_b.id}/watch/{event_b}/progress",
            json={"position": 1800.0},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Batch fetch
        resp = client.post(
            "/media/watch/states-by-film",
            json={"film_ids": [film_a.id, film_b.id, film_c.id]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()

        assert body["states"][str(film_a.id)]["has_state"] is True
        assert body["states"][str(film_a.id)]["last_position"] == 100.0

        assert body["states"][str(film_b.id)]["has_state"] is True
        assert body["states"][str(film_b.id)]["last_position"] == 1800.0

        assert body["states"][str(film_c.id)]["has_state"] is False

    def test_incognito_excluded_from_states_by_film(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Incognito watch events are excluded from states-by-film."""
        token = _register_user(client, "inc_sbf", "pass")

        film = Film(title="Incognito SBF", year=2020)
        db_session.add(film)
        db_session.flush()
        edition = MovieEdition(film_id=film.id)
        db_session.add(edition)
        db_session.flush()
        media = MediaFile(
            edition_id=edition.id, file_path="/tmp/inc_sbf.mkv",
            duration_secs=100.0,
        )
        db_session.add(media)
        db_session.commit()

        # Enable incognito
        client.put(
            "/me/incognito",
            headers={"Authorization": f"Bearer {token}"},
            json={"incognito": True},
        )

        # Start watch (creates incognito event)
        client.post(
            f"/media/{media.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )

        # States-by-film should not show it
        resp = client.post(
            "/media/watch/states-by-film",
            json={"film_ids": [film.id]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        state = resp.json()["states"][str(film.id)]
        assert state["has_state"] is False


class TestAdjacentEpisode:
    """GET /media/{id}/adjacent — prev/next episode navigation."""

    def _make_series_episode(
        self,
        db_session: Session,
        series: Series,
        season: int,
        episode: int,
        *,
        title: str = "Test",
    ) -> tuple[Film, MediaFile]:
        """Create a series episode film with one media file."""
        film = Film(
            title=title,
            year=2020,
            series_id=series.id,
            season_number=season,
            episode_number=episode,
        )
        db_session.add(film)
        db_session.flush()
        edition = MovieEdition(film_id=film.id)
        db_session.add(edition)
        db_session.flush()
        media = MediaFile(
            edition_id=edition.id,
            file_path=f"/tmp/series_{series.id}_s{season}e{episode}.mkv",
        )
        db_session.add(media)
        db_session.flush()
        return film, media

    def test_media_not_found(self, client: TestClient) -> None:
        """Non-existent media_id returns 404."""
        resp = client.get("/media/99999/adjacent")
        assert resp.status_code == 404

    def test_not_an_episode(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Regular film without series returns null fields."""
        film = Film(title="Standalone Movie", year=2020)
        db_session.add(film)
        db_session.flush()
        edition = MovieEdition(film_id=film.id)
        db_session.add(edition)
        db_session.flush()
        media = MediaFile(
            edition_id=edition.id,
            file_path="/tmp/movie.mp4",
        )
        db_session.add(media)
        db_session.commit()

        resp = client.get(f"/media/{media.id}/adjacent")
        assert resp.status_code == 200
        body = resp.json()
        assert body["series_id"] is None
        assert body["prev_media_id"] is None
        assert body["next_media_id"] is None
        assert body["season_number"] is None
        assert body["episode_number"] is None

    def test_first_episode(
        self, client: TestClient, db_session: Session
    ) -> None:
        """First episode has prev=null, next=non-null."""
        series = Series(title="Test Series")
        db_session.add(series)
        db_session.flush()

        ep1, m1 = self._make_series_episode(db_session, series, 1, 1, title="Ep 1")
        ep2, m2 = self._make_series_episode(db_session, series, 1, 2, title="Ep 2")
        ep3, m3 = self._make_series_episode(db_session, series, 1, 3, title="Ep 3")
        db_session.commit()

        resp = client.get(f"/media/{m1.id}/adjacent")
        assert resp.status_code == 200
        body = resp.json()
        assert body["series_id"] == series.id
        assert body["series_title"] == "Test Series"
        assert body["prev_media_id"] is None
        assert body["next_media_id"] == m2.id
        assert body["next_title"] is not None
        assert body["season_number"] == 1
        assert body["episode_number"] == 1

    def test_middle_episode(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Middle episode has both prev and next."""
        series = Series(title="Middle Series")
        db_session.add(series)
        db_session.flush()

        ep1, m1 = self._make_series_episode(db_session, series, 1, 1, title="Ep 1")
        ep2, m2 = self._make_series_episode(db_session, series, 1, 2, title="Ep 2")
        ep3, m3 = self._make_series_episode(db_session, series, 1, 3, title="Ep 3")
        db_session.commit()

        resp = client.get(f"/media/{m2.id}/adjacent")
        assert resp.status_code == 200
        body = resp.json()
        assert body["prev_media_id"] == m1.id
        assert body["next_media_id"] == m3.id
        assert body["episode_number"] == 2

    def test_last_episode(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Last episode has prev=non-null, next=null."""
        series = Series(title="Last Series")
        db_session.add(series)
        db_session.flush()

        ep1, m1 = self._make_series_episode(db_session, series, 1, 1, title="Ep 1")
        ep2, m2 = self._make_series_episode(db_session, series, 1, 2, title="Ep 2")
        db_session.commit()

        resp = client.get(f"/media/{m2.id}/adjacent")
        assert resp.status_code == 200
        body = resp.json()
        assert body["prev_media_id"] == m1.id
        assert body["next_media_id"] is None

    def test_multi_season_does_not_cross_boundaries(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Episodes in different seasons are not adjacent to each other."""
        series = Series(title="Multi Season")
        db_session.add(series)
        db_session.flush()

        # Season 1: 2 episodes, Season 2: 2 episodes
        s1e1, m1 = self._make_series_episode(db_session, series, 1, 1, title="S1E1")
        s1e2, m2 = self._make_series_episode(db_session, series, 1, 2, title="S1E2")
        s2e1, m3 = self._make_series_episode(db_session, series, 2, 1, title="S2E1")
        s2e2, m4 = self._make_series_episode(db_session, series, 2, 2, title="S2E2")
        db_session.commit()

        # Last in S1 — next should be null (S2E1 is different season)
        resp = client.get(f"/media/{m2.id}/adjacent")
        body = resp.json()
        assert body["next_media_id"] is None
        assert body["prev_media_id"] == m1.id

        # First in S2 — prev should be null (S1E2 is different season)
        resp = client.get(f"/media/{m3.id}/adjacent")
        body = resp.json()
        assert body["prev_media_id"] is None
        assert body["next_media_id"] == m4.id


def _register_user(client: TestClient, username: str, password: str) -> str:
    """Register a user and return token."""
    resp = client.post(
        "/auth/register",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 201
    token: str = resp.json()["access_token"]
    return token
