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
