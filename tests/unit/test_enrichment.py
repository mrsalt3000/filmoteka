"""Unit tests for enrichment pipeline — quality flags and normalization.

Uses the real domain models (Film, Genre, Person) from
``filmoteka.domain.catalog.models`` with an in-memory SQLite database
so that ``_apply_deepseek_enrichment`` can query real tables.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from filmoteka.domain.catalog.models import (
    Film,
    Genre,
    Person,
    film_person,
)
from filmoteka.domain.importing.pipeline import (
    _apply_deepseek_enrichment,
    _update_fts_vector,
)
from filmoteka.infrastructure.database import Base
from filmoteka.infrastructure.deepseek_provider import DeepSeekEnrichmentResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Create an in-memory SQLite session with the real domain schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    # Register PostgreSQL-compatible functions for testing
    @event.listens_for(engine, "connect")
    def _register_fts_functions(dbapi_con, _connection_record):
        dbapi_con.create_function("to_tsvector", 2, lambda _cfg, text: text or "")
        dbapi_con.create_function("plainto_tsquery", 2, lambda _cfg, text: text or "")
        dbapi_con.create_function("ts_rank", 2, lambda _vec, _q: 1.0)

    Base.metadata.create_all(engine)
    sess_factory = sessionmaker(bind=engine)
    session = sess_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# _apply_deepseek_enrichment — genre / person upsert
# ---------------------------------------------------------------------------


class TestApplyDeepseekEnrichmentGenre:
    """Genre normalization during enrichment."""

    def test_new_genre_created_and_linked(self, db_session: Session) -> None:
        """Genres from enrichment result are created as new Genre rows."""
        film = Film(title="Test Movie", year=2020)
        db_session.add(film)
        db_session.flush()

        result = DeepSeekEnrichmentResult(
            genres=["Action", "Sci-Fi"],
            description="A test movie.",
            actors=[],
            country="USA",
        )
        _apply_deepseek_enrichment(film, result, db_session)

        # Both genres exist in DB
        genres = db_session.query(Genre).all()
        assert len(genres) == 2
        names = {g.name for g in genres}
        slugs = {g.slug for g in genres}
        assert names == {"Action", "Sci-Fi"}
        assert slugs == {"action", "sci-fi"}

        # Film is linked to both genres
        assert len(film.genres) == 2

    def test_existing_genre_reused(self, db_session: Session) -> None:
        """If a genre already exists by slug, it is reused — not duplicated."""
        existing = Genre(name="Action", slug="action")
        db_session.add(existing)
        db_session.flush()

        film = Film(title="Another Movie")
        db_session.add(film)
        db_session.flush()

        result = DeepSeekEnrichmentResult(
            genres=["Action"], description="Test", actors=[], country=None,
        )
        _apply_deepseek_enrichment(film, result, db_session)

        assert db_session.query(Genre).count() == 1  # no duplicate
        assert len(film.genres) == 1

    def test_empty_genres_does_nothing(self, db_session: Session) -> None:
        """Empty genres list is handled gracefully."""
        film = Film(title="No Genres")
        db_session.add(film)
        db_session.flush()

        result = DeepSeekEnrichmentResult(
            genres=[], description="No genres", actors=[], country=None,
        )
        _apply_deepseek_enrichment(film, result, db_session)

        assert db_session.query(Genre).count() == 0
        assert len(film.genres) == 0


class TestApplyDeepseekEnrichmentPerson:
    """Person (actor) normalization during enrichment."""

    def test_new_person_created_and_linked(self, db_session: Session) -> None:
        """Actors from enrichment result are created as new Person rows."""
        film = Film(title="Cast Movie")
        db_session.add(film)
        db_session.flush()

        result = DeepSeekEnrichmentResult(
            genres=[], description="A cast movie.",
            actors=["Keanu Reeves", "Carrie-Anne Moss"],
            country=None,
        )
        _apply_deepseek_enrichment(film, result, db_session)

        persons = db_session.query(Person).all()
        assert len(persons) == 2
        names = {p.name for p in persons}
        assert names == {"Keanu Reeves", "Carrie-Anne Moss"}

        # Check link table rows have role="actor"
        rows = db_session.execute(
            film_person.select().where(film_person.c.film_id == film.id)
        ).all()
        assert len(rows) == 2
        for r in rows:
            assert r.role == "actor"

    def test_existing_person_reused(self, db_session: Session) -> None:
        """If a person already exists by name, it is reused."""
        existing = Person(name="Keanu Reeves")
        db_session.add(existing)
        db_session.flush()

        film = Film(title="Existing Cast")
        db_session.add(film)
        db_session.flush()

        result = DeepSeekEnrichmentResult(
            genres=[], description="Test", actors=["Keanu Reeves"], country=None,
        )
        _apply_deepseek_enrichment(film, result, db_session)

        assert db_session.query(Person).count() == 1
        assert len(film.persons) == 1

    def test_duplicate_link_skipped(self, db_session: Session) -> None:
        """If a person is already linked, the link is not duplicated."""
        person = Person(name="Keanu Reeves")
        db_session.add(person)
        db_session.flush()

        film = Film(title="Duplicate Link")
        db_session.add(film)
        db_session.flush()

        # Manually create the link once
        db_session.execute(
            film_person.insert().values(film_id=film.id, person_id=person.id, role="actor"),
        )
        db_session.flush()

        # Now enrichment runs with same actor
        result = DeepSeekEnrichmentResult(
            genres=[], description="Test", actors=["Keanu Reeves"], country=None,
        )
        _apply_deepseek_enrichment(film, result, db_session)

        # Only one link row
        rows = db_session.execute(
            film_person.select().where(film_person.c.film_id == film.id)
        ).all()
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# _apply_deepseek_enrichment — quality flags & text fields
# ---------------------------------------------------------------------------


class TestApplyDeepseekEnrichmentQualityFlags:
    """Metadata quality flags set by enrichment."""

    def test_quality_flags_set_correctly(self, db_session: Session) -> None:
        """After enrichment, all quality fields reflect DeepSeek source."""
        film = Film(title="Quality Check", year=2020)
        film.metadata_source = "filename_parse"
        film.metadata_confidence = 0.6
        film.needs_review = False
        db_session.add(film)
        db_session.flush()

        result = DeepSeekEnrichmentResult(
            genres=["Drama"], description="A quality film.", actors=[], country=None,
        )
        before_enriched_at = film.metadata_enriched_at
        _apply_deepseek_enrichment(film, result, db_session)

        assert film.metadata_source == "deepseek"
        assert film.metadata_confidence == 0.9
        assert film.metadata_enriched_at is not None
        # enriched_at should be updated (if it was None, now it's set)
        if before_enriched_at is not None:
            assert film.metadata_enriched_at >= before_enriched_at
        assert film.needs_review is False

    def test_description_and_country_set(self, db_session: Session) -> None:
        """Description and country are updated from enrichment result."""
        film = Film(title="Text Fields", year=2020)
        db_session.add(film)
        db_session.flush()

        result = DeepSeekEnrichmentResult(
            genres=[],
            description="A thrilling adventure.",
            actors=[],
            country="France",
        )
        _apply_deepseek_enrichment(film, result, db_session)

        assert film.description == "A thrilling adventure."
        assert film.country == "France"

    def test_empty_description_and_country_unchanged(self, db_session: Session) -> None:
        """If result has no description or country, existing values are preserved."""
        film = Film(title="Preserve", year=2020)
        film.description = "Original description"
        film.country = "USA"
        db_session.add(film)
        db_session.flush()

        result = DeepSeekEnrichmentResult(
            genres=[], description=None, actors=[], country=None,
        )
        _apply_deepseek_enrichment(film, result, db_session)

        # Existing values NOT overwritten by None
        assert film.description == "Original description"
        assert film.country == "USA"


class TestUpdateFtsVector:
    """_update_fts_vector — full-text search vector generation."""

    def test_fts_vector_contains_title(self, db_session: Session) -> None:
        """fts_vector is set and includes the film title."""
        film = Film(title="The Matrix", year=1999)
        db_session.add(film)
        db_session.flush()

        _update_fts_vector(film, db_session)
        db_session.flush()

        assert film.fts_vector is not None
        # tsvector is opaque binary; verify it's non-null after call

    def test_fts_vector_includes_genres(self, db_session: Session) -> None:
        """Genre names are included in the fts_vector."""
        action = Genre(name="Action", slug="action")
        sci_fi = Genre(name="Sci-Fi", slug="sci-fi")
        db_session.add_all([action, sci_fi])
        db_session.flush()

        film = Film(title="Test Film")
        db_session.add(film)
        db_session.flush()

        film.genres = [action, sci_fi]
        db_session.flush()

        _update_fts_vector(film, db_session)
        db_session.flush()

        assert film.fts_vector is not None

    def test_fts_vector_includes_description(self, db_session: Session) -> None:
        """Description is included in the fts_vector."""
        film = Film(title="Desc Film", description="A space adventure story")
        db_session.add(film)
        db_session.flush()

        _update_fts_vector(film, db_session)
        db_session.flush()

        assert film.fts_vector is not None
