"""Integration tests for catalog endpoints."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from filmoteka.app import create_app
from filmoteka.domain.catalog.models import Film
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
