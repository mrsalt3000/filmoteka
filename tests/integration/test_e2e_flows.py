"""End-to-end tests covering main user flows through the full stack."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from filmoteka.app import create_app
from filmoteka.domain.catalog.models import Film, Genre, MediaFile, MovieEdition, Person
from filmoteka.infrastructure.database import get_db

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c


# ═══════════════════════════════════════════════════════════════════
# 1. Catalog page
# ═══════════════════════════════════════════════════════════════════

class TestCatalogPage:
    """User opens the catalog page in a browser."""

    def test_home_page_loads(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert "<!DOCTYPE html>" in html
        assert "Filmoteka" in html
        assert "film-grid" in html
        assert "search" in html

    def test_films_api_returns_data(
        self, client: TestClient, db_session: Session
    ) -> None:
        db_session.add_all([
            Film(title="E2E Film 1", year=2000),
            Film(title="E2E Film 2", year=2001),
        ])
        db_session.commit()

        resp = client.get("/films")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        titles = {f["title"] for f in data["items"]}
        assert titles == {"E2E Film 1", "E2E Film 2"}


# ═══════════════════════════════════════════════════════════════════
# 2. Film card
# ═══════════════════════════════════════════════════════════════════

class TestFilmCard:
    """User clicks on a film and sees its details with related data."""

    def test_film_card_with_related_data(
        self, client: TestClient, db_session: Session
    ) -> None:
        # Arrange: film with genre, person, edition, media file
        genre = Genre(name="Sci-Fi", slug="sci-fi")
        person = Person(name="Director Name")
        db_session.add_all([genre, person])
        db_session.flush()

        film = Film(title="E2E Film", year=2020, description="Test")
        film.genres.append(genre)
        db_session.add(film)
        db_session.flush()

        # Add person with role via association table
        from filmoteka.domain.catalog.models import film_person
        db_session.execute(
            film_person.insert().values(
                film_id=film.id, person_id=person.id, role="director"
            )
        )

        edition = MovieEdition(
            film_id=film.id, edition_name="Extended", quality="1080p", language="en"
        )
        db_session.add(edition)
        db_session.flush()

        media = MediaFile(
            edition_id=edition.id,
            file_path="/tmp/e2e_test.mkv",
            file_size=500_000_000,
            duration_secs=6000.0,
            width=1920,
            height=1080,
            codec="h264",
        )
        db_session.add(media)
        db_session.commit()

        # Act: fetch the film card
        resp = client.get(f"/films/{film.id}")
        assert resp.status_code == 200

        # Assert: all related data present
        body = resp.json()
        assert body["title"] == "E2E Film"
        assert body["year"] == 2020
        assert body["description"] == "Test"
        assert len(body["genres"]) == 1
        assert body["genres"][0]["name"] == "Sci-Fi"
        assert len(body["persons"]) == 1
        assert body["persons"][0]["name"] == "Director Name"
        assert body["persons"][0]["role"] == "director"
        assert len(body["editions"]) == 1
        assert body["editions"][0]["quality"] == "1080p"
        assert len(body["editions"][0]["media_files"]) == 1
        assert body["editions"][0]["media_files"][0]["codec"] == "h264"
        assert body["editions"][0]["media_files"][0]["width"] == 1920

    def test_film_not_found(self, client: TestClient) -> None:
        resp = client.get("/films/99999")
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# 3. Watch flow (start → state → progress → history)
# ═══════════════════════════════════════════════════════════════════

class TestWatchFlow:
    """User registers, opens a film, starts watching, and resumes later."""

    def _register(self, client: TestClient) -> str:
        resp = client.post(
            "/auth/register",
            json={"username": "e2e_user", "password": "secret123"},
        )
        assert resp.status_code == 201
        token: str = resp.json()["access_token"]
        return token

    def _make_media(self, db_session: Session) -> tuple[int, int]:
        """Create a minimal film+edition+media and return (film_id, media_id)."""
        film = Film(title="E2E Watchable", year=2020)
        db_session.add(film)
        db_session.flush()
        edition = MovieEdition(film_id=film.id)
        db_session.add(edition)
        db_session.flush()
        media = MediaFile(
            edition_id=edition.id,
            file_path="/tmp/e2e_watch.mkv",
            file_size=100,
        )
        db_session.add(media)
        db_session.commit()
        return film.id, media.id

    def test_full_watch_lifecycle(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = self._register(client)
        film_id, media_id = self._make_media(db_session)
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Check state — no watch yet
        resp = client.get(f"/media/{media_id}/watch/state", headers=headers)
        assert resp.json()["has_state"] is False

        # 2. Start watching
        resp = client.post(
            f"/media/{media_id}/watch/start", headers=headers
        )
        assert resp.status_code == 200
        event_id = resp.json()["watch_event_id"]
        assert resp.json()["last_position"] == 0.0

        # 3. Check state again — now has position
        resp = client.get(f"/media/{media_id}/watch/state", headers=headers)
        assert resp.json()["has_state"] is True
        assert resp.json()["watch_event_id"] == event_id

        # 4. Update progress
        resp = client.patch(
            f"/media/{media_id}/watch/{event_id}/progress",
            json={"position": 123.0},
            headers=headers,
        )
        assert resp.status_code == 200

        # 5. Verify progress persisted via state
        resp = client.get(f"/media/{media_id}/watch/state", headers=headers)
        assert resp.json()["last_position"] == 123.0

        # 6. Check watch history
        resp = client.get("/me/watch/history", headers=headers)
        assert resp.status_code == 200
        history = resp.json()
        assert history["total"] >= 1
        # Most recent item should be our film
        latest = history["items"][0]
        assert latest["media_file_id"] == media_id
        assert latest["film_title"] == "E2E Watchable"
        assert latest["last_position"] == 123.0
        assert latest["finished"] is False
        assert "started_at" in latest

    def test_watch_requires_auth(self, client: TestClient) -> None:
        resp = client.post("/media/1/watch/start")
        assert resp.status_code == 401

        resp = client.get("/media/1/watch/state")
        assert resp.status_code == 401

        resp = client.patch("/media/1/watch/1/progress", json={"position": 0})
        assert resp.status_code == 401

        resp = client.get("/me/watch/history")
        assert resp.status_code == 401
