"""Integration tests for user endpoints — watch history."""

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
)
from filmoteka.domain.watching.models import WatchEvent
from filmoteka.infrastructure.database import get_db

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as c:
        yield c


def _register(client: TestClient, username: str, password: str = "pass123") -> str:
    resp = client.post(
        "/auth/register",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 201
    token: str = resp.json()["access_token"]
    return token


def _make_media(
    db_session: Session,
    film_title: str = "Film",
    year: int | None = 2000,
    file_path: str | None = None,
) -> MediaFile:
    film = Film(title=film_title, year=year)
    db_session.add(film)
    db_session.flush()
    edition = MovieEdition(film_id=film.id)
    db_session.add(edition)
    db_session.flush()
    path = file_path or f"/tmp/m_{film_title}.mkv"
    media = MediaFile(edition_id=edition.id, file_path=path, file_size=100)
    db_session.add(media)
    db_session.commit()
    return media


class TestWatchHistory:
    """GET /me/watch/history"""

    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/me/watch/history")
        assert resp.status_code == 401

    def test_empty_history(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "histempty")
        resp = client.get(
            "/me/watch/history",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"items": [], "total": 0}

    def test_single_entry(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "singlehist")
        media = _make_media(db_session, film_title="The History", year=1999)

        # Start watch
        resp = client.post(
            f"/media/{media.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        event_id = resp.json()["watch_event_id"]

        # Get history
        resp = client.get(
            "/me/watch/history",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        item = body["items"][0]
        assert item["watch_event_id"] == event_id
        assert item["media_file_id"] == media.id
        assert item["film_title"] == "The History"
        assert item["film_year"] == 1999
        assert item["finished"] is False

    def test_multiple_entries_order(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "multihist")
        media1 = _make_media(db_session, film_title="First", year=2000)
        media2 = _make_media(db_session, film_title="Second", year=2001)

        # Start two watches (in order)
        client.post(
            f"/media/{media1.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )
        client.post(
            f"/media/{media2.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        )

        resp = client.get(
            "/me/watch/history",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = resp.json()
        assert body["total"] == 2
        # Most recent first
        assert body["items"][0]["film_title"] == "Second"
        assert body["items"][1]["film_title"] == "First"

    def test_mix_finished_and_unfinished(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "mixed")
        media1 = _make_media(db_session, film_title="Watched", file_path="/tmp/w1.mkv")
        media2 = _make_media(db_session, film_title="Partial", file_path="/tmp/w2.mkv")

        # Start both
        r1 = client.post(
            f"/media/{media1.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        client.post(
            f"/media/{media2.id}/watch/start",
            headers={"Authorization": f"Bearer {token}"},
        ).json()

        # Finish the first one
        event1 = db_session.get(WatchEvent, r1["watch_event_id"])
        assert event1 is not None
        event1.finished = True
        db_session.commit()

        # History should contain both
        resp = client.get(
            "/me/watch/history",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = resp.json()
        assert body["total"] == 2
        finished_items = [i for i in body["items"] if i["finished"]]
        unfinished_items = [i for i in body["items"] if not i["finished"]]
        assert len(finished_items) == 1
        assert len(unfinished_items) == 1
        assert finished_items[0]["film_title"] == "Watched"
        assert unfinished_items[0]["film_title"] == "Partial"

    def test_other_user_not_visible(
        self, client: TestClient, db_session: Session
    ) -> None:
        token_a = _register(client, "usera")
        token_b = _register(client, "userb")

        media = _make_media(db_session)
        # User A starts watching
        client.post(
            f"/media/{media.id}/watch/start",
            headers={"Authorization": f"Bearer {token_a}"},
        )

        # User B sees empty history
        resp = client.get(
            "/me/watch/history",
            headers={"Authorization": f"Bearer {token_b}"},
        )
        assert resp.json()["total"] == 0

    def test_pagination(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "paginat")
        media_ids = []
        for i in range(5):
            m = _make_media(db_session, film_title=f"F{i}")
            media_ids.append(m.id)
            client.post(
                f"/media/{m.id}/watch/start",
                headers={"Authorization": f"Bearer {token}"},
            )

        resp = client.get(
            "/me/watch/history?skip=1&limit=2",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = resp.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2


# ── Blacklist ────────────────────────────────────────────────────


def _create_film(db_session: Session, title: str = "Test Film") -> Film:
    f = Film(title=title, year=2020)
    db_session.add(f)
    db_session.commit()
    return f


class TestBlacklist:
    """Blacklist endpoints — POST/DELETE /me/blacklist and GET /me/blacklist."""

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_without_token_gets_401(self, client: TestClient) -> None:
        resp = client.get("/me/blacklist")
        assert resp.status_code == 401

    def test_list_empty(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "bl_empty")
        resp = client.get("/me/blacklist", headers=self._auth(token))
        assert resp.status_code == 200
        assert resp.json() == {"film_ids": []}

    def test_add_and_list(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "bl_addlist")
        f = _create_film(db_session, "Blacklist Me")

        resp = client.post(
            f"/me/blacklist/{f.id}",
            headers=self._auth(token),
        )
        assert resp.status_code == 204

        resp = client.get("/me/blacklist", headers=self._auth(token))
        assert resp.json() == {"film_ids": [f.id]}

    def test_add_nonexistent_film_returns_404(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "bl_notfound")
        resp = client.post(
            "/me/blacklist/99999",
            headers=self._auth(token),
        )
        assert resp.status_code == 404

    def test_add_idempotent(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "bl_idem")
        f = _create_film(db_session)

        # Add twice
        client.post(f"/me/blacklist/{f.id}", headers=self._auth(token))
        resp2 = client.post(
            f"/me/blacklist/{f.id}",
            headers=self._auth(token),
        )
        assert resp2.status_code == 204

        resp = client.get("/me/blacklist", headers=self._auth(token))
        assert resp.json() == {"film_ids": [f.id]}

    def test_remove(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "bl_remove")
        f = _create_film(db_session)

        client.post(f"/me/blacklist/{f.id}", headers=self._auth(token))
        resp = client.delete(
            f"/me/blacklist/{f.id}",
            headers=self._auth(token),
        )
        assert resp.status_code == 204

        resp = client.get("/me/blacklist", headers=self._auth(token))
        assert resp.json() == {"film_ids": []}

    def test_remove_idempotent(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "bl_remidem")
        f = _create_film(db_session)

        # Remove without adding first
        resp = client.delete(
            f"/me/blacklist/{f.id}",
            headers=self._auth(token),
        )
        assert resp.status_code == 204

        resp = client.get("/me/blacklist", headers=self._auth(token))
        assert resp.json() == {"film_ids": []}

    def test_user_isolation(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Two users have separate blacklists."""
        t1 = _register(client, "bl_iso1")
        t2 = _register(client, "bl_iso2")
        f = _create_film(db_session)

        client.post(f"/me/blacklist/{f.id}", headers=self._auth(t1))

        r1 = client.get("/me/blacklist", headers=self._auth(t1))
        r2 = client.get("/me/blacklist", headers=self._auth(t2))
        assert r1.json() == {"film_ids": [f.id]}
        assert r2.json() == {"film_ids": []}

    def test_blacklist_excludes_from_catalog(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Blacklisted film does not appear in GET /films."""
        token = _register(client, "bl_cat")
        f = _create_film(db_session, "Hidden Film")

        # Before blacklist — film is visible
        resp = client.get("/films", headers=self._auth(token))
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Hidden Film" in titles

        # Add to blacklist
        client.post(f"/me/blacklist/{f.id}", headers=self._auth(token))

        # After blacklist — film is hidden
        resp = client.get("/films", headers=self._auth(token))
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Hidden Film" not in titles

    def test_blacklist_does_not_affect_other_users(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Film blacklisted by user A is still visible to user B."""
        t_a = _register(client, "bl_aff_a")
        t_b = _register(client, "bl_aff_b")
        f = _create_film(db_session, "Shared Film")

        client.post(f"/me/blacklist/{f.id}", headers=self._auth(t_a))

        resp = client.get("/films", headers=self._auth(t_b))
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Shared Film" in titles


# ── Incognito mode ───────────────────────────────────────────────


def _make_incognito_media(db_session: Session) -> MediaFile:
    f = Film(title="Incognito Test Film", year=2020)
    db_session.add(f)
    db_session.flush()
    ed = MovieEdition(film_id=f.id)
    db_session.add(ed)
    db_session.flush()
    m = MediaFile(edition_id=ed.id, file_path="/tmp/incognito_test.mp4", duration_secs=120)
    db_session.add(m)
    db_session.commit()
    return m


class TestIncognito:
    """Incognito mode — PUT /me/incognito and effect on history."""

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_set_incognito_on(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "inc_on")
        resp = client.put(
            "/me/incognito",
            headers=self._auth(token),
            json={"incognito": True},
        )
        assert resp.status_code == 200
        assert resp.json()["incognito"] is True

    def test_set_incognito_off(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "inc_off")
        client.put(
            "/me/incognito",
            headers=self._auth(token),
            json={"incognito": True},
        )
        resp = client.put(
            "/me/incognito",
            headers=self._auth(token),
            json={"incognito": False},
        )
        assert resp.json()["incognito"] is False

    def test_incognito_watch_not_in_history(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Watch event created in incognito mode does not appear in history."""
        token = _register(client, "inc_hist")
        media = _make_incognito_media(db_session)

        # Enable incognito
        client.put(
            "/me/incognito",
            headers=self._auth(token),
            json={"incognito": True},
        )

        # Start watching
        client.post(
            f"/media/{media.id}/watch/start",
            headers=self._auth(token),
        )

        # History should be empty
        resp = client.get(
            "/me/watch/history",
            headers=self._auth(token),
        )
        assert resp.json()["total"] == 0

    def test_non_incognito_watch_in_history(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Watch event created without incognito appears in history."""
        token = _register(client, "inc_nohist")
        media = _make_incognito_media(db_session)

        client.post(
            f"/media/{media.id}/watch/start",
            headers=self._auth(token),
        )

        resp = client.get(
            "/me/watch/history",
            headers=self._auth(token),
        )
        assert resp.json()["total"] == 1


# ── Clear history ────────────────────────────────────────────────


class TestClearHistory:
    """DELETE /me/watch/history and /me/watch/history/{film_id}."""

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_clear_all(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "clr_all")
        media = _make_incognito_media(db_session)
        client.post(f"/media/{media.id}/watch/start", headers=self._auth(token))

        resp = client.delete(
            "/me/watch/history",
            headers=self._auth(token),
        )
        assert resp.status_code == 204

        hist = client.get("/me/watch/history", headers=self._auth(token))
        assert hist.json()["total"] == 0

    def test_clear_all_idempotent(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "clr_idem")
        resp = client.delete(
            "/me/watch/history",
            headers=self._auth(token),
        )
        assert resp.status_code == 204

    def test_clear_all_requires_auth(
        self, client: TestClient
    ) -> None:
        resp = client.delete("/me/watch/history")
        assert resp.status_code == 401

    def test_clear_by_film(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "clr_film")

        # Create two films with media
        f1 = Film(title="Film One", year=2020)
        f2 = Film(title="Film Two", year=2021)
        db_session.add_all([f1, f2])
        db_session.flush()

        ed1 = MovieEdition(film_id=f1.id)
        ed2 = MovieEdition(film_id=f2.id)
        db_session.add_all([ed1, ed2])
        db_session.flush()

        m1 = MediaFile(edition_id=ed1.id, file_path="/a/one.mp4")
        m2 = MediaFile(edition_id=ed2.id, file_path="/b/two.mp4")
        db_session.add_all([m1, m2])
        db_session.commit()

        # Watch both
        client.post(f"/media/{m1.id}/watch/start", headers=self._auth(token))
        client.post(f"/media/{m2.id}/watch/start", headers=self._auth(token))

        hist = client.get("/me/watch/history", headers=self._auth(token))
        assert hist.json()["total"] == 2

        # Clear only film one
        resp = client.delete(
            f"/me/watch/history/{f1.id}",
            headers=self._auth(token),
        )
        assert resp.status_code == 204

        hist = client.get("/me/watch/history", headers=self._auth(token))
        assert hist.json()["total"] == 1

    def test_clear_by_film_nonexistent(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "clr_nf")
        resp = client.delete(
            "/me/watch/history/99999",
            headers=self._auth(token),
        )
        assert resp.status_code == 204  # idempotent


# ── Exclude family from recommendations ─────────────────────────


class TestExcludeFamily:
    """PUT /me/exclude-family — toggle flag."""

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_default_is_true(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "ef_default")
        resp = client.get("/auth/me", headers=self._auth(token))
        assert resp.json()["exclude_family_from_recommendations"] is True

    def test_set_false(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "ef_false")
        resp = client.put(
            "/me/exclude-family",
            headers=self._auth(token),
            json={"exclude": False},
        )
        assert resp.status_code == 200
        assert resp.json()["exclude_family_from_recommendations"] is False

    def test_set_true(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "ef_true")
        client.put(
            "/me/exclude-family",
            headers=self._auth(token),
            json={"exclude": False},
        )
        resp = client.put(
            "/me/exclude-family",
            headers=self._auth(token),
            json={"exclude": True},
        )
        assert resp.json()["exclude_family_from_recommendations"] is True

    def test_requires_auth(
        self, client: TestClient
    ) -> None:
        resp = client.put("/me/exclude-family", json={"exclude": True})
        assert resp.status_code == 401


# ── Include external ─────────────────────────────────────────────


class TestIncludeExternal:
    """PUT /me/include-external — toggle flag."""

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_default_is_false(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "ext_default")
        resp = client.get("/auth/me", headers=self._auth(token))
        assert resp.json()["include_external"] is False

    def test_set_true(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "ext_true")
        resp = client.put(
            "/me/include-external",
            headers=self._auth(token),
            json={"include": True},
        )
        assert resp.status_code == 200
        assert resp.json()["include_external"] is True

    def test_set_false(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "ext_false")
        client.put(
            "/me/include-external",
            headers=self._auth(token),
            json={"include": True},
        )
        resp = client.put(
            "/me/include-external",
            headers=self._auth(token),
            json={"include": False},
        )
        assert resp.json()["include_external"] is False

    def test_requires_auth(
        self, client: TestClient
    ) -> None:
        resp = client.put("/me/include-external", json={"include": True})
        assert resp.status_code == 401


# ── Language filter ──────────────────────────────────────────────


class TestFilterByLanguage:
    """PUT /me/filter-by-language — toggle flag."""

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_default_is_false(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "lang_default")
        resp = client.get("/auth/me", headers=self._auth(token))
        assert resp.json()["filter_by_language"] is False

    def test_set_true(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "lang_true")
        resp = client.put(
            "/me/filter-by-language",
            headers=self._auth(token),
            json={"filter": True},
        )
        assert resp.status_code == 200
        assert resp.json()["filter_by_language"] is True

    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.put("/me/filter-by-language", json={"filter": True})
        assert resp.status_code == 401


# ── Recommendations ──────────────────────────────────────────────


class TestRecommendations:
    """GET /me/recommendations — personalized recommendations."""

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.get("/me/recommendations")
        assert resp.status_code == 401

    def test_no_history_returns_empty(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "rec_empty")
        resp = client.get(
            "/me/recommendations",
            headers=self._auth(token),
        )
        assert resp.json() == {"items": [], "total": 0}

    def test_recommends_by_genre(
        self, client: TestClient, db_session: Session
    ) -> None:
        """After watching a Sci-Fi film, another Sci-Fi film is recommended."""
        token = _register(client, "rec_genre")

        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        drama = Genre(name="Drama", slug="drama")
        db_session.add_all([sci_fi, drama])
        db_session.flush()

        watched = Film(title="Watched Sci-Fi", year=2020, genres=[sci_fi])
        candidate = Film(title="Another Sci-Fi", year=2021, genres=[sci_fi])
        unrelated = Film(title="A Drama", year=2022, genres=[drama])
        db_session.add_all([watched, candidate, unrelated])
        db_session.flush()

        # Create a media file + watch event for the watched film
        ed = MovieEdition(film_id=watched.id)
        db_session.add(ed)
        db_session.flush()
        m = MediaFile(edition_id=ed.id, file_path="/tmp/rec_sci.mkv")
        db_session.add(m)
        db_session.commit()

        # Mark as finished
        client.post(
            f"/media/{m.id}/watch/start",
            headers=self._auth(token),
        )
        # Update directly to finished
        event = db_session.query(WatchEvent).first()
        assert event is not None
        event.finished = True
        db_session.commit()

        resp = client.get(
            "/me/recommendations",
            headers=self._auth(token),
        )
        assert resp.status_code == 200
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Another Sci-Fi" in titles
        assert "A Drama" not in titles  # different genre
        assert "Watched Sci-Fi" not in titles  # already watched

    def test_excludes_blacklisted(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Blacklisted film is not recommended even if genre matches."""
        token = _register(client, "rec_bl")

        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        db_session.add(sci_fi)
        db_session.flush()

        watched = Film(title="Watched", year=2020, genres=[sci_fi])
        blacklisted = Film(title="Blacklisted Sci-Fi", year=2021, genres=[sci_fi])
        db_session.add_all([watched, blacklisted])
        db_session.flush()

        ed = MovieEdition(film_id=watched.id)
        db_session.add(ed)
        db_session.flush()
        m = MediaFile(edition_id=ed.id, file_path="/tmp/rec_bl.mkv")
        db_session.add(m)
        db_session.commit()

        client.post(f"/media/{m.id}/watch/start", headers=self._auth(token))
        event = db_session.query(WatchEvent).first()
        event.finished = True
        db_session.commit()

        # Blacklist the candidate
        client.post(
            f"/me/blacklist/{blacklisted.id}",
            headers=self._auth(token),
        )

        resp = client.get(
            "/me/recommendations",
            headers=self._auth(token),
        )
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Blacklisted Sci-Fi" not in titles

    def test_excludes_family_video(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Family video not recommended when exclude_family is True (default)."""
        token = _register(client, "rec_fam")

        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        db_session.add(sci_fi)
        db_session.flush()

        watched = Film(title="Watched", year=2020, genres=[sci_fi])
        family = Film(title="Family Fun", year=2021, genres=[sci_fi], is_family_video=True)
        normal = Film(title="Normal Film", year=2022, genres=[sci_fi])
        db_session.add_all([watched, family, normal])
        db_session.flush()

        ed = MovieEdition(film_id=watched.id)
        db_session.add(ed)
        db_session.flush()
        m = MediaFile(edition_id=ed.id, file_path="/tmp/rec_fam.mkv")
        db_session.add(m)
        db_session.commit()

        client.post(f"/media/{m.id}/watch/start", headers=self._auth(token))
        event = db_session.query(WatchEvent).first()
        event.finished = True
        db_session.commit()

        resp = client.get("/me/recommendations", headers=self._auth(token))
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Normal Film" in titles
        assert "Family Fun" not in titles

    def test_excludes_already_watched(
        self, client: TestClient, db_session: Session
    ) -> None:
        """In-progress (not finished) watch also excluded."""
        token = _register(client, "rec_aw")

        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        db_session.add(sci_fi)
        db_session.flush()

        watched = Film(title="Watched Unfinished", year=2020, genres=[sci_fi])
        other = Film(title="Other Film", year=2021, genres=[sci_fi])
        db_session.add_all([watched, other])
        db_session.flush()

        ed = MovieEdition(film_id=watched.id)
        db_session.add(ed)
        db_session.flush()
        m = MediaFile(edition_id=ed.id, file_path="/tmp/rec_aw.mkv")
        db_session.add(m)
        db_session.commit()

        # Start but don't finish
        client.post(f"/media/{m.id}/watch/start", headers=self._auth(token))

        resp = client.get("/me/recommendations", headers=self._auth(token))
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Watched Unfinished" not in titles
        assert "Other Film" not in titles  # no finished film to score from

    def test_respects_child_age_restrictions(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Child with age_group=7_12 does not get 18+ recommendations."""
        admin_token = _register(client, "rec_child_admin")
        db_session.query(User).filter(User.username == "rec_child_admin").update(
            {"role": "admin"}
        )
        db_session.commit()

        create = client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"username": "rec_child", "password": "pass",
                  "role": "child", "age_group": "7_12"},
        )
        assert create.status_code == 201
        child_token = client.post("/auth/login", json={
            "username": "rec_child", "password": "pass",
        }).json()["access_token"]

        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        db_session.add(sci_fi)
        db_session.flush()

        safe = Film(title="Safe Sci-Fi", year=2020, genres=[sci_fi], age_rating="6+")
        adult = Film(title="Adult Sci-Fi", year=2021, genres=[sci_fi], age_rating="18+")
        db_session.add_all([safe, adult])

        # Child needs to have watched something for recommendations
        watched = Film(title="Watched Kid", year=2019, genres=[sci_fi])
        db_session.add(watched)
        db_session.flush()
        ed = MovieEdition(film_id=watched.id)
        db_session.add(ed)
        db_session.flush()
        m = MediaFile(edition_id=ed.id, file_path="/tmp/rec_kid.mkv")
        db_session.add(m)
        db_session.commit()
        client.post(f"/media/{m.id}/watch/start", headers={"Authorization": f"Bearer {child_token}"})
        event = db_session.query(WatchEvent).filter(
            WatchEvent.media_file_id == m.id
        ).first()
        if event:
            event.finished = True
            db_session.commit()

        resp = client.get("/me/recommendations", headers={"Authorization": f"Bearer {child_token}"})
        assert resp.status_code == 200
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Safe Sci-Fi" in titles
        assert "Adult Sci-Fi" not in titles

    def test_incognito_not_counted(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Incognito watch events do not affect recommendations."""
        token = _register(client, "rec_inc")

        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        db_session.add(sci_fi)
        db_session.flush()

        watched = Film(title="Incognito Watch", year=2020, genres=[sci_fi])
        candidate = Film(title="Candidate", year=2021, genres=[sci_fi])
        db_session.add_all([watched, candidate])
        db_session.flush()

        ed = MovieEdition(film_id=watched.id)
        db_session.add(ed)
        db_session.flush()
        m = MediaFile(edition_id=ed.id, file_path="/tmp/rec_inc.mkv")
        db_session.add(m)
        db_session.commit()

        # Enable incognito, watch, disable incognito
        client.put("/me/incognito", headers=self._auth(token), json={"incognito": True})
        client.post(f"/media/{m.id}/watch/start", headers=self._auth(token))
        client.put("/me/incognito", headers=self._auth(token), json={"incognito": False})

        # No recommendations because incognito watch doesn't count
        resp = client.get("/me/recommendations", headers=self._auth(token))
        assert resp.json()["total"] == 0


class TestRecommendByMood:
    """POST /me/recommendations/by-mood — mood-based suggestions."""

    @pytest.fixture(autouse=True)
    def _no_deepseek(self) -> Generator[None, None, None]:
        """Prevent DeepSeek from intercepting keyword/LLM path tests."""
        from unittest.mock import patch

        from filmoteka.infrastructure.settings import settings

        with patch.object(settings, "deepseek_api_key", None):
            yield

    def _auth(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_requires_auth(self, client: TestClient) -> None:
        resp = client.post(
            "/me/recommendations/by-mood",
            json={"query": "comedy"},
        )
        assert resp.status_code == 401

    def test_returns_matching_genre(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "mood_test")
        comedy = Genre(name="Comedy", slug="comedy")
        drama = Genre(name="Drama", slug="drama")
        db_session.add_all([comedy, drama])
        db_session.flush()
        db_session.add_all([
            Film(title="Funny Movie", year=2020, genres=[comedy]),
            Film(title="Sad Movie", year=2021, genres=[drama]),
        ])
        db_session.commit()

        resp = client.post(
            "/me/recommendations/by-mood",
            headers=self._auth(token),
            json={"query": "comedy"},
        )
        assert resp.status_code == 200
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Funny Movie" in titles
        assert "Sad Movie" not in titles

    def test_unknown_mood_returns_empty(
        self, client: TestClient, db_session: Session
    ) -> None:
        token = _register(client, "mood_empty")
        resp = client.post(
            "/me/recommendations/by-mood",
            headers=self._auth(token),
            json={"query": "xyznonexistent"},
        )
        assert resp.json() == {"items": [], "total": 0}

    def test_fallback_no_llm(
        self, client: TestClient, db_session: Session
    ) -> None:
        """Without LLM_API_URL, by-mood uses keyword fallback."""
        from filmoteka.infrastructure.settings import settings
        from unittest.mock import patch

        with patch.object(settings, "llm_api_url", None):
            comedy = Genre(name="Comedy", slug="comedy")
            db_session.add(comedy)
            db_session.flush()
            db_session.add(Film(title="Funny", year=2020, genres=[comedy]))
            db_session.commit()

            token = _register(client, "mood_fallback1")
            resp = client.post(
                "/me/recommendations/by-mood",
                headers={"Authorization": f"Bearer {token}"},
                json={"query": "comedy"},
            )
            assert resp.status_code == 200
            titles = [i["title"] for i in resp.json()["items"]]
            assert "Funny" in titles

    def test_fallback_llm_unreachable(
        self, client: TestClient, db_session: Session
    ) -> None:
        """With LLM_API_URL set to unreachable, falls back to keywords."""
        from filmoteka.infrastructure.settings import settings
        from unittest.mock import patch

        comedy = Genre(name="Comedy", slug="comedy")
        db_session.add(comedy)
        db_session.flush()
        db_session.add(Film(title="Funny", year=2020, genres=[comedy]))
        db_session.commit()

        token = _register(client, "mood_fallback2")
        with patch.object(settings, "llm_api_url", "http://localhost:19999"):
            resp = client.post(
                "/me/recommendations/by-mood",
                headers={"Authorization": f"Bearer {token}"},
                json={"query": "comedy"},
            )
        assert resp.status_code == 200
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Funny" in titles

    def test_deepseek_returns_recommendations(
        self, client: TestClient, db_session: Session
    ) -> None:
        """With DEEPSEEK_API_KEY, DeepSeek path is used."""
        from unittest.mock import patch

        from filmoteka.infrastructure.settings import settings

        db_session.add(Film(title="The Matrix", year=1999))
        db_session.add(Film(title="Inception", year=2010))
        db_session.commit()

        token = _register(client, "mood_deepseek1")

        # Mock urlopen to return a controlled response
        class FakeResponse:
            status = 200

            def read(self) -> bytes:
                return b'{"choices":[{"message":{"content":"The Matrix\\nInception"}}]}'

            def __enter__(self) -> FakeResponse:
                return self

            def __exit__(self, *args: object) -> None:
                pass

        with (
            patch.object(settings, "deepseek_api_key", "sk-fake"),
            patch("urllib.request.urlopen", return_value=FakeResponse()),
        ):
            resp = client.post(
                "/me/recommendations/by-mood",
                headers={"Authorization": f"Bearer {token}"},
                json={"query": "action"},
            )

        assert resp.status_code == 200
        titles = [i["title"] for i in resp.json()["items"]]
        assert "The Matrix" in titles
        assert "Inception" in titles

    def test_deepseek_unreachable_falls_back_to_keywords(
        self, client: TestClient, db_session: Session
    ) -> None:
        """DeepSeek unreachable -> falls back to keyword path."""
        from unittest.mock import patch

        from filmoteka.infrastructure.settings import settings

        comedy = Genre(name="Comedy", slug="comedy")
        db_session.add(comedy)
        db_session.flush()
        db_session.add(Film(title="Funny", year=2020, genres=[comedy]))
        db_session.commit()

        token = _register(client, "mood_deepseek2")

        # urlopen to an unreachable port will raise URLError -> fall through
        with (
            patch.object(settings, "deepseek_api_key", "sk-fake"),
            patch.object(settings, "llm_api_url", None),
            patch("urllib.request.urlopen", side_effect=Exception("unreachable")),
        ):
            resp = client.post(
                "/me/recommendations/by-mood",
                headers={"Authorization": f"Bearer {token}"},
                json={"query": "comedy"},
            )

        assert resp.status_code == 200
        titles = [i["title"] for i in resp.json()["items"]]
        assert "Funny" in titles
