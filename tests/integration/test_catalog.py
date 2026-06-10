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

    # ── Filters: genre, year range ────────────────────────────────

    def test_filter_by_genre_slug(
        self, client: TestClient, db_session: Session
    ) -> None:
        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        drama = Genre(name="Drama", slug="drama")
        action = Genre(name="Action", slug="action")
        f1 = Film(title="Interstellar", year=2014, genres=[sci_fi])
        f2 = Film(title="The Dark Knight", year=2008, genres=[action, drama])
        f3 = Film(title="Inception", year=2010, genres=[sci_fi, action])
        db_session.add_all([f1, f2, f3])
        db_session.commit()

        resp = client.get("/films?genre=sci-fi")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        titles = {f["title"] for f in body["items"]}
        assert titles == {"Interstellar", "Inception"}

    def test_filter_by_genre_slug_no_results(
        self, client: TestClient, db_session: Session
    ) -> None:
        comedy = Genre(name="Comedy", slug="comedy")
        f1 = Film(title="Interstellar", year=2014, genres=[comedy])
        db_session.add(f1)
        db_session.commit()

        resp = client.get("/films?genre=horror")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0

    def test_filter_by_year_from(
        self, client: TestClient, db_session: Session
    ) -> None:
        db_session.add_all([
            Film(title="Old", year=1999),
            Film(title="Middle", year=2005),
            Film(title="New", year=2010),
        ])
        db_session.commit()

        resp = client.get("/films?year_from=2000")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert {f["title"] for f in body["items"]} == {"Middle", "New"}

    def test_filter_by_year_to(
        self, client: TestClient, db_session: Session
    ) -> None:
        db_session.add_all([
            Film(title="Old", year=1999),
            Film(title="Middle", year=2005),
            Film(title="New", year=2010),
        ])
        db_session.commit()

        resp = client.get("/films?year_to=2005")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert {f["title"] for f in body["items"]} == {"Old", "Middle"}

    def test_filter_by_year_range(
        self, client: TestClient, db_session: Session
    ) -> None:
        db_session.add_all([
            Film(title="Old", year=1999),
            Film(title="Middle", year=2005),
            Film(title="New", year=2010),
            Film(title="Latest", year=2020),
        ])
        db_session.commit()

        resp = client.get("/films?year_from=2000&year_to=2010")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert {f["title"] for f in body["items"]} == {"Middle", "New"}

    def test_filter_genre_plus_year_range(
        self, client: TestClient, db_session: Session
    ) -> None:
        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        drama = Genre(name="Drama", slug="drama")
        f1 = Film(title="Interstellar", year=2014, genres=[sci_fi])
        f2 = Film(title="The Martian", year=2015, genres=[sci_fi, drama])
        f3 = Film(title="Arrival", year=2016, genres=[sci_fi])
        f4 = Film(title="Inception", year=2010, genres=[sci_fi])
        db_session.add_all([f1, f2, f3, f4])
        db_session.commit()

        resp = client.get("/films?genre=sci-fi&year_from=2014&year_to=2015")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert {f["title"] for f in body["items"]} == {"Interstellar", "The Martian"}

    def test_filter_combined_with_search(
        self, client: TestClient, db_session: Session
    ) -> None:
        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        drama = Genre(name="Drama", slug="drama")
        f1 = Film(title="Interstellar", year=2014, genres=[sci_fi])
        f2 = Film(title="The Dark Knight", year=2008, genres=[drama])
        db_session.add_all([f1, f2])
        db_session.commit()

        resp = client.get("/films?genre=sci-fi&q=inter")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Interstellar"

    # ── Tech attribute filters: resolution, codec, audio_codec, subtitles ──

    def test_filter_by_resolution(
        self, client: TestClient, db_session: Session
    ) -> None:
        f1 = Film(title="HD Film", year=2020)
        f2 = Film(title="SD Film", year=2021)
        db_session.add_all([f1, f2])
        db_session.flush()

        ed1 = MovieEdition(film_id=f1.id)
        ed2 = MovieEdition(film_id=f2.id)
        db_session.add_all([ed1, ed2])
        db_session.flush()

        db_session.add_all([
            MediaFile(edition_id=ed1.id, file_path="/a/hd.mp4", height=1080, codec="h264"),
            MediaFile(edition_id=ed2.id, file_path="/b/sd.mp4", height=480, codec="h264"),
        ])
        db_session.commit()

        resp = client.get("/films?resolution=720")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "HD Film"

    def test_filter_by_resolution_4k(
        self, client: TestClient, db_session: Session
    ) -> None:
        f1 = Film(title="4K Film", year=2022)
        f2 = Film(title="1080p Film", year=2023)
        db_session.add_all([f1, f2])
        db_session.flush()

        ed1 = MovieEdition(film_id=f1.id)
        ed2 = MovieEdition(film_id=f2.id)
        db_session.add_all([ed1, ed2])
        db_session.flush()

        db_session.add_all([
            MediaFile(edition_id=ed1.id, file_path="/a/4k.mp4", height=2160),
            MediaFile(edition_id=ed2.id, file_path="/b/1080.mp4", height=1080),
        ])
        db_session.commit()

        resp = client.get("/films?resolution=4k")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "4K Film"

    def test_filter_by_codec(
        self, client: TestClient, db_session: Session
    ) -> None:
        f1 = Film(title="H264 Film", year=2020)
        f2 = Film(title="HEVC Film", year=2021)
        db_session.add_all([f1, f2])
        db_session.flush()

        ed1 = MovieEdition(film_id=f1.id)
        ed2 = MovieEdition(film_id=f2.id)
        db_session.add_all([ed1, ed2])
        db_session.flush()

        db_session.add_all([
            MediaFile(edition_id=ed1.id, file_path="/a/h264.mp4", codec="h264"),
            MediaFile(edition_id=ed2.id, file_path="/b/hevc.mp4", codec="hevc"),
        ])
        db_session.commit()

        resp = client.get("/films?codec=h264")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "H264 Film"

    def test_filter_by_codec_partial(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Partial match on codec (e.g. '264' matches 'h264')."""
        f1 = Film(title="H264 Film", year=2020)
        db_session.add(f1)
        db_session.flush()

        ed1 = MovieEdition(film_id=f1.id)
        db_session.add(ed1)
        db_session.flush()

        db_session.add(MediaFile(edition_id=ed1.id, file_path="/a/h264.mp4", codec="h264"))
        db_session.commit()

        resp = client.get("/films?codec=264")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1

    def test_filter_by_audio_codec(
        self, client: TestClient, db_session: Session
    ) -> None:
        f1 = Film(title="AAC Film", year=2020)
        f2 = Film(title="DTS Film", year=2021)
        db_session.add_all([f1, f2])
        db_session.flush()

        ed1 = MovieEdition(film_id=f1.id)
        ed2 = MovieEdition(film_id=f2.id)
        db_session.add_all([ed1, ed2])
        db_session.flush()

        db_session.add_all([
            MediaFile(edition_id=ed1.id, file_path="/a/aac.mp4", audio_codec="aac"),
            MediaFile(edition_id=ed2.id, file_path="/b/dts.mp4", audio_codec="dts"),
        ])
        db_session.commit()

        resp = client.get("/films?audio_codec=aac")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "AAC Film"

    def test_filter_has_subtitles(
        self, client: TestClient, db_session: Session
    ) -> None:
        f1 = Film(title="With Subs", year=2020)
        f2 = Film(title="No Subs", year=2021)
        db_session.add_all([f1, f2])
        db_session.flush()

        ed1 = MovieEdition(film_id=f1.id)
        ed2 = MovieEdition(film_id=f2.id)
        db_session.add_all([ed1, ed2])
        db_session.flush()

        db_session.add_all([
            MediaFile(edition_id=ed1.id, file_path="/a/subs.mp4", subtitle_languages="eng,rus"),
            MediaFile(edition_id=ed2.id, file_path="/b/nosubs.mp4", subtitle_languages=None),
        ])
        db_session.commit()

        resp = client.get("/films?has_subtitles=true")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "With Subs"

    def test_filter_combined_tech(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Combine resolution + codec filter."""
        f1 = Film(title="HD H264", year=2020)
        f2 = Film(title="HD HEVC", year=2021)
        db_session.add_all([f1, f2])
        db_session.flush()

        ed1 = MovieEdition(film_id=f1.id)
        ed2 = MovieEdition(film_id=f2.id)
        db_session.add_all([ed1, ed2])
        db_session.flush()

        db_session.add_all([
            MediaFile(edition_id=ed1.id, file_path="/a/hd_h264.mp4", height=1080, codec="h264"),
            MediaFile(edition_id=ed2.id, file_path="/b/hd_hevc.mp4", height=1080, codec="hevc"),
        ])
        db_session.commit()

        resp = client.get("/films?resolution=1080&codec=hevc")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "HD HEVC"

    # ── Full-text search: description, genres, persons ─────────────

    def test_search_by_description(
        self, client: TestClient, db_session: Session
    ) -> None:
        db_session.add_all([
            Film(title="Alpha", description="A thrilling space adventure"),
            Film(title="Beta", description="A quiet drama"),
        ])
        db_session.commit()

        resp = client.get("/films?q=space+adventure")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Alpha"

    def test_search_by_genre(
        self, client: TestClient, db_session: Session
    ) -> None:
        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        drama = Genre(name="Drama", slug="drama")
        f1 = Film(title="Interstellar", year=2014, genres=[sci_fi])
        f2 = Film(title="The Father", year=2020, genres=[drama])
        db_session.add_all([f1, f2])
        db_session.commit()

        resp = client.get("/films?q=sci-fi")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Interstellar"

    def test_search_by_actor(
        self, client: TestClient, db_session: Session
    ) -> None:
        from filmoteka.domain.catalog.models import film_person

        actor = Person(name="Keanu Reeves")
        other = Person(name="Tom Hanks")
        db_session.add_all([actor, other])
        db_session.flush()

        f1 = Film(title="The Matrix")
        f2 = Film(title="Forrest Gump")
        db_session.add_all([f1, f2])
        db_session.flush()

        db_session.execute(
            film_person.insert().values([
                {"film_id": f1.id, "person_id": actor.id, "role": "actor"},
                {"film_id": f2.id, "person_id": other.id, "role": "actor"},
            ])
        )
        db_session.commit()

        resp = client.get("/films?q=keanu")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "The Matrix"

    def test_search_matches_multiple_fields(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Search term can match via different fields for different films."""
        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        f1 = Film(title="The Matrix", year=1999, description="A sci-fi classic")
        f2 = Film(title="Inception", year=2010, description="Dream heist")
        db_session.add_all([f1, f2])
        db_session.flush()
        f1.genres = [sci_fi]
        db_session.commit()

        # "sci-fi" matches f1 by description and f1 by genre
        resp = client.get("/films?q=sci-fi")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1


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
        assert body["needs_review"] is False

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

    def test_needs_review_flag(
        self, client: TestClient, db_session: Session
    ) -> None:
        film = Film(title="Suspicious", year=1999, needs_review=True)
        db_session.add(film)
        db_session.commit()

        resp = client.get(f"/films/{film.id}")
        assert resp.status_code == 200
        assert resp.json()["needs_review"] is True

    def test_bare_film_needs_review_default(
        self, client: TestClient, db_session: Session
    ) -> None:
        film = Film(title="Clean", year=2000)
        db_session.add(film)
        db_session.commit()

        resp = client.get(f"/films/{film.id}")
        assert resp.status_code == 200
        assert resp.json()["needs_review"] is False
