"""Integration tests for media streaming endpoints."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from filmoteka.app import create_app
from filmoteka.domain.catalog.models import Film, MediaFile, MovieEdition
from filmoteka.infrastructure.database import get_db

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient with DB dependency overridden to the integration test DB."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c


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
