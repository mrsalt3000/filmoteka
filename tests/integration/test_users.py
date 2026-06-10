"""Integration tests for user endpoints — watch history."""

from __future__ import annotations

from collections.abc import Generator

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
