"""Integration tests for catalog endpoints."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from filmoteka.app import create_app
from filmoteka.domain.catalog.models import (
    Film,
    Genre,
    MediaFile,
    MovieEdition,
    Person,
)
from filmoteka.infrastructure.database import get_db

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient with DB dependency overridden to the integration test DB."""
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c


class TestListFilms:
    """GET /films"""

    def test_empty_list(self, client: TestClient) -> None:
        resp = client.get("/films")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"items": [], "total": 0}

    def test_single_film(self, client: TestClient, db_session: Session) -> None:
        db_session.add(Film(title="The Matrix", year=1999))
        db_session.commit()

        resp = client.get("/films")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["title"] == "The Matrix"
        assert body["items"][0]["year"] == 1999
        assert "id" in body["items"][0]
        assert "created_at" in body["items"][0]
        # poster_url is exposed in the list response
        assert body["items"][0]["poster_url"] is None

    def test_multiple_films(self, client: TestClient, db_session: Session) -> None:
        db_session.add_all([
            Film(title="A", year=2000),
            Film(title="B", year=2001),
            Film(title="C", year=2002),
        ])
        db_session.commit()

        resp = client.get("/films")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3

    def test_filter_by_year(self, client: TestClient, db_session: Session) -> None:
        db_session.add_all([
            Film(title="Film 2000", year=2000),
            Film(title="Film 2001", year=2001),
            Film(title="Film 2000 v2", year=2000),
        ])
        db_session.commit()

        resp = client.get("/films?year=2000")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert all(f["year"] == 2000 for f in body["items"])

    def test_pagination(self, client: TestClient, db_session: Session) -> None:
        db_session.add_all([Film(title=f"Film {i}", year=2000) for i in range(10)])
        db_session.commit()

        resp = client.get("/films?skip=3&limit=4")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 10
        assert len(body["items"]) == 4

    def test_films_ordered_by_created_at_desc(
        self, client: TestClient, db_session: Session
    ) -> None:
        # Add films one by one so created_at differs
        from datetime import datetime, timedelta

        f1 = Film(title="Oldest", year=2000)
        db_session.add(f1)
        db_session.flush()
        f1.created_at = datetime.now() - timedelta(hours=2)

        f2 = Film(title="Middle", year=2001)
        db_session.add(f2)
        db_session.flush()
        f2.created_at = datetime.now() - timedelta(hours=1)

        f3 = Film(title="Newest", year=2002)
        db_session.add(f3)
        db_session.flush()
        f3.created_at = datetime.now()

        db_session.commit()

        resp = client.get("/films?limit=10")
        body = resp.json()
        titles = [f["title"] for f in body["items"]]
        assert titles == ["Newest", "Middle", "Oldest"]

    def test_limit_clamp_to_100(self, client: TestClient, db_session: Session) -> None:
        db_session.add_all([Film(title=f"F{i}") for i in range(150)])
        db_session.commit()

        resp = client.get("/films?limit=999")
        assert resp.status_code == 422  # validation error, limit capped at 100

    def test_skip_negative_rejected(self, client: TestClient) -> None:
        resp = client.get("/films?skip=-1")
        assert resp.status_code == 422

    def test_search_by_partial_title(
        self, client: TestClient, db_session: Session
    ) -> None:
        db_session.add_all([
            Film(title="The Matrix", year=1999),
            Film(title="The Matrix Reloaded", year=2003),
            Film(title="Inception", year=2010),
        ])
        db_session.commit()

        resp = client.get("/films?q=matrix")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        titles = {f["title"] for f in body["items"]}
        assert titles == {"The Matrix", "The Matrix Reloaded"}

    def test_search_case_insensitive(
        self, client: TestClient, db_session: Session
    ) -> None:
        db_session.add(Film(title="Interstellar", year=2014))
        db_session.commit()

        resp = client.get("/films?q=INTER")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_search_empty_result(
        self, client: TestClient, db_session: Session
    ) -> None:
        db_session.add(Film(title="Something", year=2020))
        db_session.commit()

        resp = client.get("/films?q=zzzzz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_search_with_year_filter(
        self, client: TestClient, db_session: Session
    ) -> None:
        db_session.add_all([
            Film(title="The Matrix", year=1999),
            Film(title="The Matrix Reloaded", year=2003),
        ])
        db_session.commit()

        resp = client.get("/films?q=matrix&year=2003")
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "The Matrix Reloaded"


class TestGetFilm:
    """GET /films/{id}"""

    def test_not_found(self, client: TestClient) -> None:
        resp = client.get("/films/99999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Film not found"

    def test_bare_film(self, client: TestClient, db_session: Session) -> None:
        film = Film(title="Solo Film", year=2005, description="A test film")
        db_session.add(film)
        db_session.commit()

        resp = client.get(f"/films/{film.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Solo Film"
        assert body["year"] == 2005
        assert body["description"] == "A test film"
        assert body["genres"] == []
        assert body["persons"] == []
        assert body["editions"] == []
        assert body["poster_url"] is None

    def test_with_genres(self, client: TestClient, db_session: Session) -> None:
        g1 = Genre(name="Sci-Fi", slug="sci-fi")
        g2 = Genre(name="Action", slug="action")
        film = Film(title="Multi-Genre", year=2020, genres=[g1, g2])
        db_session.add(film)
        db_session.commit()

        resp = client.get(f"/films/{film.id}")
        body = resp.json()
        assert len(body["genres"]) == 2
        slugs = {g["slug"] for g in body["genres"]}
        assert slugs == {"sci-fi", "action"}

    def test_with_persons(
        self, client: TestClient, db_session: Session
    ) -> None:
        actor = Person(name="Jane Doe")
        director = Person(name="John Smith")
        db_session.add_all([actor, director])
        db_session.flush()

        film = Film(title="Starring...", year=2021)
        db_session.add(film)
        db_session.flush()

        # Insert into the association table with explicit roles
        from filmoteka.domain.catalog.models import film_person

        db_session.execute(
            film_person.insert().values(
                [
                    {"film_id": film.id, "person_id": actor.id, "role": "actor"},
                    {"film_id": film.id, "person_id": director.id, "role": "director"},
                ]
            )
        )
        db_session.commit()

        resp = client.get(f"/films/{film.id}")
        body = resp.json()
        assert len(body["persons"]) == 2
        roles = {(p["name"], p["role"]) for p in body["persons"]}
        assert ("Jane Doe", "actor") in roles
        assert ("John Smith", "director") in roles

    def test_with_editions_and_media(
        self, client: TestClient, db_session: Session
    ) -> None:
        film = Film(title="With Files", year=2022)
        db_session.add(film)
        db_session.flush()

        edition = MovieEdition(
            film_id=film.id,
            edition_name="Director's Cut",
            quality="1080p",
            language="en",
        )
        db_session.add(edition)
        db_session.flush()

        media = MediaFile(
            edition_id=edition.id,
            file_path="/media/library/2022/With Files (2022)/film.mkv",
            file_size=1_000_000_000,
            duration_secs=7200.0,
            width=1920,
            height=1080,
            codec="h264",
        )
        db_session.add(media)
        db_session.commit()

        resp = client.get(f"/films/{film.id}")
        body = resp.json()
        assert len(body["editions"]) == 1
        ed = body["editions"][0]
        assert ed["edition_name"] == "Director's Cut"
        assert ed["quality"] == "1080p"
        assert len(ed["media_files"]) == 1
        mf = ed["media_files"][0]
        assert mf["file_path"] == media.file_path
        assert mf["width"] == 1920
        assert mf["codec"] == "h264"
