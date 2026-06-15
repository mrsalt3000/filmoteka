"""Integration tests for catalog endpoints."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from filmoteka.app import create_app
from filmoteka.domain.access.models import User
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

    # ── Language filters (audio_lang, subtitle_lang) ──────────────

    def test_filter_audio_lang(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Filter by audio language code."""
        f1 = Film(title="Russian Audio", year=2020)
        f2 = Film(title="English Audio", year=2021)
        db_session.add_all([f1, f2])
        db_session.flush()

        ed1 = MovieEdition(film_id=f1.id)
        ed2 = MovieEdition(film_id=f2.id)
        db_session.add_all([ed1, ed2])
        db_session.flush()

        db_session.add_all([
            MediaFile(edition_id=ed1.id, file_path="/a/rus.mp4", audio_codec="rus"),
            MediaFile(edition_id=ed2.id, file_path="/b/eng.mp4", audio_codec="eng"),
        ])
        db_session.commit()

        resp = client.get("/films?audio_lang=rus")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Russian Audio"

    def test_filter_subtitle_lang(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Filter by subtitle language code."""
        f1 = Film(title="English Subs", year=2020)
        f2 = Film(title="No Subs", year=2021)
        db_session.add_all([f1, f2])
        db_session.flush()

        ed1 = MovieEdition(film_id=f1.id)
        ed2 = MovieEdition(film_id=f2.id)
        db_session.add_all([ed1, ed2])
        db_session.flush()

        db_session.add_all([
            MediaFile(edition_id=ed1.id, file_path="/a/en_subs.mkv",
                      subtitle_languages="eng,rus"),
            MediaFile(edition_id=ed2.id, file_path="/b/no_subs.mkv",
                      subtitle_languages=None),
        ])
        db_session.commit()

        resp = client.get("/films?subtitle_lang=eng")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "English Subs"

    def test_filter_audio_lang_no_results(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Audio language filter returns empty when nothing matches."""
        db_session.add(Film(title="Only English", year=2020))
        db_session.flush()
        ed = MovieEdition(film_id=db_session.query(Film).one().id)
        db_session.add(ed)
        db_session.flush()
        db_session.add(MediaFile(edition_id=ed.id, file_path="/a/en.mp4",
                                 audio_codec="eng"))
        db_session.commit()

        resp = client.get("/films?audio_lang=fre")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0

    def test_filter_subtitle_lang_partial(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Subtitle language filter works with partial match."""
        f1 = Film(title="Multi Sub", year=2020)
        db_session.add(f1)
        db_session.flush()
        ed = MovieEdition(film_id=f1.id)
        db_session.add(ed)
        db_session.flush()
        db_session.add(MediaFile(edition_id=ed.id, file_path="/a/multi.mkv",
                                 subtitle_languages="eng,fre,ger,spa"))
        db_session.commit()

        resp = client.get("/films?subtitle_lang=ger")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Multi Sub"

    # ── Cross-category filter combinations ────────────────────────

    def test_search_plus_genre(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Search text + genre slug combo."""
        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        drama = Genre(name="Drama", slug="drama")
        f1 = Film(title="Interstellar", year=2014, genres=[sci_fi],
                   description="Space exploration")
        f2 = Film(title="Arrival", year=2016, genres=[sci_fi],
                   description="Alien linguistics")
        f3 = Film(title="The Father", year=2020, genres=[drama])
        db_session.add_all([f1, f2, f3])
        db_session.commit()

        resp = client.get("/films?q=space&genre=sci-fi")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Interstellar"

    def test_search_plus_codec(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Search text + tech attribute combo."""
        f1 = Film(title="The Matrix", year=1999, description="Reality is a simulation")
        f2 = Film(title="Matrix Reloaded", year=2003, description="More reality")
        db_session.add_all([f1, f2])
        db_session.flush()

        ed1 = MovieEdition(film_id=f1.id)
        ed2 = MovieEdition(film_id=f2.id)
        db_session.add_all([ed1, ed2])
        db_session.flush()

        db_session.add_all([
            MediaFile(edition_id=ed1.id, file_path="/a/matrix.mkv", codec="hevc"),
            MediaFile(edition_id=ed2.id, file_path="/b/reloaded.mkv", codec="h264"),
        ])
        db_session.commit()

        resp = client.get("/films?q=matrix&codec=hevc")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "The Matrix"

    def test_year_from_gt_year_to(
        self, client: TestClient, db_session: Session
    ) -> None:
        """year_from > year_to returns empty result."""
        db_session.add_all([
            Film(title="Old", year=2000),
            Film(title="New", year=2020),
        ])
        db_session.commit()

        resp = client.get("/films?year_from=2020&year_to=2010")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0

    def test_audio_plus_subtitle_lang(
        self, client: TestClient, db_session: Session
    ) -> None:
        """audio_lang + subtitle_lang combo."""
        f1 = Film(title="Russian with Eng subs", year=2020)
        f2 = Film(title="English only", year=2021)
        db_session.add_all([f1, f2])
        db_session.flush()

        ed1 = MovieEdition(film_id=f1.id)
        ed2 = MovieEdition(film_id=f2.id)
        db_session.add_all([ed1, ed2])
        db_session.flush()

        db_session.add_all([
            MediaFile(edition_id=ed1.id, file_path="/a/rus_eng.mkv",
                      audio_codec="rus", subtitle_languages="eng"),
            MediaFile(edition_id=ed2.id, file_path="/b/eng.mkv",
                      audio_codec="eng", subtitle_languages=None),
        ])
        db_session.commit()

        resp = client.get("/films?audio_lang=rus&subtitle_lang=eng")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Russian with Eng subs"

    def test_genre_plus_resolution(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Genre slug + resolution combo."""
        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        action = Genre(name="Action", slug="action")
        f1 = Film(title="Sci-Fi HD", year=2020, genres=[sci_fi])
        f2 = Film(title="Action HD", year=2021, genres=[action])
        db_session.add_all([f1, f2])
        db_session.flush()

        ed1 = MovieEdition(film_id=f1.id)
        ed2 = MovieEdition(film_id=f2.id)
        db_session.add_all([ed1, ed2])
        db_session.flush()

        db_session.add_all([
            MediaFile(edition_id=ed1.id, file_path="/a/sci.mkv", height=1080),
            MediaFile(edition_id=ed2.id, file_path="/b/act.mkv", height=1080),
        ])
        db_session.commit()

        resp = client.get("/films?genre=sci-fi&resolution=1080")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Sci-Fi HD"

    # ── Child age-restriction filtering ───────────────────────────

    def _auth_header(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _create_user(
        self, client: TestClient, username: str, password: str = "pass"
    ) -> str:
        resp = client.post(
            "/auth/register",
            json={"username": username, "password": password},
        )
        assert resp.status_code == 201
        return resp.json()["access_token"]

    def _make_admin(self, db_session: Session, username: str) -> None:
        user = db_session.query(User).filter(User.username == username).first()
        if user is not None:
            user.role = "admin"
            db_session.commit()

    def test_child_with_age_group_filters_adult_content(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Child with age_group=7_12 cannot see 18+ films."""
        f1 = Film(title="Cartoon", year=2020, age_rating="0+")
        f2 = Film(title="Teen Movie", year=2021, age_rating="12+")
        f3 = Film(title="Adult Only", year=2022, age_rating="18+")
        db_session.add_all([f1, f2, f3])
        db_session.commit()

        # Create admin, then use it to create a child
        admin_token = self._create_user(client, "admin_for_child")
        self._make_admin(db_session, "admin_for_child")

        create = client.post(
            "/admin/users",
            headers=self._auth_header(admin_token),
            json={
                "username": "test_kid",
                "password": "pass",
                "role": "child",
                "age_group": "7_12",
            },
        )
        assert create.status_code == 201

        # Login as the child
        login = client.post(
            "/auth/login",
            json={"username": "test_kid", "password": "pass"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        # Child fetches films — should only see 0+ and 12+, not 18+
        resp = client.get("/films", headers=self._auth_header(token))
        assert resp.status_code == 200
        body = resp.json()
        titles = [item["title"] for item in body["items"]]
        assert "Cartoon" in titles
        assert "Teen Movie" in titles
        assert "Adult Only" not in titles

    def test_child_without_age_group_sees_all(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Child without age_group set sees everything."""
        db_session.add(Film(title="Any Film", year=2020, age_rating="18+"))
        db_session.commit()

        # Create admin, create child without age_group
        admin_token = self._create_user(client, "admin_cnoage")
        self._make_admin(db_session, "admin_cnoage")

        create = client.post(
            "/admin/users",
            headers=self._auth_header(admin_token),
            json={"username": "child_no_age", "password": "pass", "role": "child"},
        )
        assert create.status_code == 201

        login = client.post(
            "/auth/login",
            json={"username": "child_no_age", "password": "pass"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        resp = client.get("/films", headers=self._auth_header(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1

    def test_adult_user_sees_all(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Regular user (not child) sees all films regardless of age_rating."""
        db_session.add(Film(title="Adult Film", year=2020, age_rating="18+"))
        db_session.commit()

        token = self._create_user(client, "adult_viewer")
        resp = client.get("/films", headers=self._auth_header(token))
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1

    def test_exclude_watched_hides_started_films(
        self, client: TestClient, db_session: Session
    ) -> None:
        """When exclude_watched is ON, started films are hidden from listing."""
        token = self._create_user(client, "ew_user")
        f = Film(title="Watched Film", year=2020)
        db_session.add(f)
        db_session.flush()
        ed = MovieEdition(film_id=f.id)
        db_session.add(ed)
        db_session.flush()
        m = MediaFile(edition_id=ed.id, file_path="/tmp/ew.mkv")
        db_session.add(m)
        db_session.commit()

        # Start watching
        client.post(f"/media/{m.id}/watch/start", headers=self._auth_header(token))

        # Toggle exclude_watched ON
        client.put(
            "/me/exclude-watched",
            headers=self._auth_header(token),
            json={"exclude": True},
        )

        # Film should be hidden
        resp = client.get("/films", headers=self._auth_header(token))
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Watched Film" not in titles

        # Toggle OFF — film visible again
        client.put(
            "/me/exclude-watched",
            headers=self._auth_header(token),
            json={"exclude": False},
        )
        resp = client.get("/films", headers=self._auth_header(token))
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Watched Film" in titles

    def test_age_rating_16plus_filtered(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Child with age_group=7_12 cannot see 16+ or 18+ films."""
        admin_token = self._create_user(client, "admin_16f")
        self._make_admin(db_session, "admin_16f")

        create = client.post(
            "/admin/users",
            headers=self._auth_header(admin_token),
            json={"username": "kid_16f", "password": "pass", "role": "child", "age_group": "7_12"},
        )
        assert create.status_code == 201
        login = client.post("/auth/login", json={"username": "kid_16f", "password": "pass"})
        token = login.json()["access_token"]

        db_session.add_all([
            Film(title="Safe", year=2020, age_rating="6+"),
            Film(title="Risky", year=2021, age_rating="16+"),
            Film(title="Adult", year=2022, age_rating="18+"),
        ])
        db_session.commit()

        resp = client.get("/films", headers=self._auth_header(token))
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Safe" in titles
        assert "Risky" not in titles
        assert "Adult" not in titles

    def test_age_rating_16plus_allowed_for_older(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Child with age_group=13_17 can see 16+ but not 18+."""
        admin_token = self._create_user(client, "admin_16o")
        self._make_admin(db_session, "admin_16o")

        create = client.post(
            "/admin/users",
            headers=self._auth_header(admin_token),
            json={"username": "kid_16o", "password": "pass", "role": "child", "age_group": "13_17"},
        )
        assert create.status_code == 201
        login = client.post("/auth/login", json={"username": "kid_16o", "password": "pass"})
        token = login.json()["access_token"]

        db_session.add_all([
            Film(title="Teen", year=2020, age_rating="16+"),
            Film(title="Adult", year=2021, age_rating="18+"),
        ])
        db_session.commit()

        resp = client.get("/films", headers=self._auth_header(token))
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Teen" in titles
        assert "Adult" not in titles

    def test_film_without_age_rating_visible_to_child(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Films with no age_rating are visible to children."""
        admin_token = self._create_user(client, "admin_norating")
        self._make_admin(db_session, "admin_norating")

        create = client.post(
            "/admin/users",
            headers=self._auth_header(admin_token),
            json={
                "username": "kid_norating", "password": "pass",
                "role": "child", "age_group": "0_6",
            },
        )
        assert create.status_code == 201
        login = client.post("/auth/login", json={"username": "kid_norating", "password": "pass"})
        token = login.json()["access_token"]

        db_session.add(Film(title="Unrated", year=2020))  # age_rating=None
        db_session.commit()

        resp = client.get("/films", headers=self._auth_header(token))
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Unrated" in titles

    # ── Family video ──────────────────────────────────────────────

    def test_family_video_excluded_by_default(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Family video is excluded from GET /films by default."""
        db_session.add_all([
            Film(title="Normal Movie", year=2020),
            Film(title="Family Clip", year=2021, is_family_video=True),
        ])
        db_session.commit()

        resp = client.get("/films")
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Normal Movie" in titles
        assert "Family Clip" not in titles

    def test_family_video_included_with_flag(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Family video appears when include_family=true."""
        db_session.add(Film(title="Family Clip", year=2021, is_family_video=True))
        db_session.commit()

        resp = client.get("/films?include_family=true")
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Family Clip" in titles

    def test_family_video_flag_in_detail(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Film detail exposes is_family_video flag."""
        f = Film(title="Family", year=2020, is_family_video=True)
        db_session.add(f)
        db_session.commit()

        resp = client.get(f"/films/{f.id}")
        assert resp.status_code == 200
        assert resp.json()["is_family_video"] is True

    def test_admin_can_set_family_video(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Admin can mark a film as family video via PUT /admin/films/{id}."""
        f = Film(title="Toggleable", year=2020)
        db_session.add(f)
        db_session.commit()

        admin_token = self._create_user(client, "admin_fam")
        self._make_admin(db_session, "admin_fam")

        resp = client.put(
            f"/admin/films/{f.id}",
            headers=self._auth_header(admin_token),
            json={"is_family_video": True},
        )
        assert resp.status_code == 200
        assert resp.json()["is_family_video"] is True

        # Also check detail reflects it
        detail = client.get(f"/films/{f.id}")
        assert detail.json()["is_family_video"] is True

    def test_family_excluded_from_search(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Family video excluded from search results by default."""
        db_session.add(Film(title="Birthday Party", year=2020, is_family_video=True))
        db_session.commit()

        resp = client.get("/films?q=Birthday")
        assert resp.status_code == 200
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Birthday Party" not in titles

    def test_family_visible_in_list_response(
        self, client: TestClient, db_session: Session
    ) -> None:
        """is_family_video field is exposed in the list endpoint."""
        db_session.add(Film(title="Test", year=2020, is_family_video=True))
        db_session.commit()

        resp = client.get("/films?include_family=true")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert "is_family_video" in item
        assert item["is_family_video"] is True

    def test_family_combo_with_search(
        self, client: TestClient, db_session: Session
    ) -> None:
        """include_family=true plus search finds family videos."""
        db_session.add_all([
            Film(title="Birthday Party", year=2020, is_family_video=True),
            Film(title="Other Film", year=2021),
        ])
        db_session.commit()

        resp = client.get("/films?q=Birthday&include_family=true")
        assert resp.status_code == 200
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Birthday Party" in titles

    def test_admin_toggle_removes_from_listing(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Toggling is_family_video on via admin removes it from default listing."""
        f = Film(title="Toggle Off", year=2020)
        db_session.add(f)
        db_session.commit()

        # Visible by default
        resp = client.get("/films")
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Toggle Off" in titles

        # Admin marks as family video
        admin_token = self._create_user(client, "admin_toggle_fam")
        self._make_admin(db_session, "admin_toggle_fam")
        client.put(
            f"/admin/films/{f.id}",
            headers=self._auth_header(admin_token),
            json={"is_family_video": True},
        )

        # Now hidden from default listing
        resp = client.get("/films")
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Toggle Off" not in titles

    def test_anonymous_excludes_family(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Unauthenticated users also do not see family videos."""
        db_session.add(Film(title="Private Clip", year=2020, is_family_video=True))
        db_session.commit()

        resp = client.get("/films")
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Private Clip" not in titles

    def test_catalog_works_without_omdb_key(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Catalog listing and detail work without OMDB_API_KEY."""
        from filmoteka.infrastructure.settings import settings
        from unittest.mock import patch

        with patch.object(settings, "omdb_api_key", None):
            f = Film(title="Offline Film", year=2020)
            db_session.add(f)
            db_session.commit()

            # List works
            resp = client.get("/films")
            assert resp.status_code == 200
            titles = [i["title"] for i in resp.json()["items"]]
            assert "Offline Film" in titles

            # Detail works
            resp = client.get(f"/films/{f.id}")
            assert resp.status_code == 200
            assert resp.json()["title"] == "Offline Film"

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
        assert body["age_rating"] is None
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


# ── Series API ─────────────────────────────────────────────────────


class TestListSeries:
    """GET /series"""

    def test_empty_list(self, client: TestClient) -> None:
        resp = client.get("/series")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"items": [], "total": 0}

    def test_list_with_one_series(
        self, client: TestClient, db_session: Session
    ) -> None:
        from filmoteka.domain.catalog.models import Series

        s = Series(title="My Show")
        db_session.add(s)
        db_session.flush()
        ep1 = Film(title="Pilot", year=2020, series_id=s.id,
                    season_number=1, episode_number=1)
        ep2 = Film(title="Second", year=2020, series_id=s.id,
                    season_number=1, episode_number=2)
        db_session.add_all([ep1, ep2])
        db_session.commit()

        resp = client.get("/series")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["title"] == "My Show"
        assert item["episode_count"] == 2

    def test_pagination(self, client: TestClient, db_session: Session) -> None:
        from filmoteka.domain.catalog.models import Series

        for i in range(3):
            s = Series(title=f"Series {i}")
            db_session.add(s)
        db_session.commit()

        resp = client.get("/series?skip=1&limit=2")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert len(body["items"]) == 2


class TestGetSeries:
    """GET /series/{id}"""

    def test_not_found(self, client: TestClient) -> None:
        resp = client.get("/series/99999")
        assert resp.status_code == 404

    def test_detail_with_seasons(
        self, client: TestClient, db_session: Session
    ) -> None:
        from filmoteka.domain.catalog.models import Series

        s = Series(title="Multi Season")
        db_session.add(s)
        db_session.flush()
        # Season 1
        e1 = Film(title="Pilot", year=2020, series_id=s.id,
                   season_number=1, episode_number=1)
        e2 = Film(title="Second", year=2020, series_id=s.id,
                   season_number=1, episode_number=2)
        # Season 2
        e3 = Film(title="Return", year=2021, series_id=s.id,
                   season_number=2, episode_number=1)
        db_session.add_all([e1, e2, e3])
        db_session.commit()

        resp = client.get(f"/series/{s.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["title"] == "Multi Season"
        assert body["episode_count"] == 3
        assert len(body["seasons"]) == 2
        # Season 1 has 2 episodes, Season 2 has 1
        s1 = [sg for sg in body["seasons"] if sg["season_number"] == 1][0]
        assert len(s1["episodes"]) == 2
        s2 = [sg for sg in body["seasons"] if sg["season_number"] == 2][0]
        assert len(s2["episodes"]) == 1
        assert s2["episodes"][0]["title"] == "Return"


class TestListEpisodes:
    """GET /series/{id}/episodes"""

    def test_not_found(self, client: TestClient) -> None:
        resp = client.get("/series/99999/episodes")
        assert resp.status_code == 404

    def test_all_episodes(
        self, client: TestClient, db_session: Session
    ) -> None:
        from filmoteka.domain.catalog.models import Series

        s = Series(title="Show")
        db_session.add(s)
        db_session.flush()
        eps = [
            Film(title=f"Ep {i}", year=2020, series_id=s.id,
                 season_number=1, episode_number=i)
            for i in range(1, 4)
        ]
        db_session.add_all(eps)
        db_session.commit()

        resp = client.get(f"/series/{s.id}/episodes")
        assert resp.status_code == 200
        body = resp.json()
        assert body["series_id"] == s.id
        assert body["season_number"] is None
        assert body["total"] == 3
        assert len(body["items"]) == 3

    def test_filter_by_season(
        self, client: TestClient, db_session: Session
    ) -> None:
        from filmoteka.domain.catalog.models import Series

        s = Series(title="Test")
        db_session.add(s)
        db_session.flush()
        s1 = Film(title="S1E1", series_id=s.id,
                   season_number=1, episode_number=1)
        s2 = Film(title="S2E1", series_id=s.id,
                   season_number=2, episode_number=1)
        db_session.add_all([s1, s2])
        db_session.commit()

        resp = client.get(f"/series/{s.id}/episodes?season=1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["season_number"] == 1
        assert body["items"][0]["title"] == "S1E1"

    def test_pagination(
        self, client: TestClient, db_session: Session
    ) -> None:
        from filmoteka.domain.catalog.models import Series

        s = Series(title="Long")
        db_session.add(s)
        db_session.flush()
        eps = [
            Film(title=f"Ep {i}", series_id=s.id,
                 season_number=1, episode_number=i)
            for i in range(1, 6)
        ]
        db_session.add_all(eps)
        db_session.commit()

        resp = client.get(f"/series/{s.id}/episodes?skip=2&limit=2")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2
