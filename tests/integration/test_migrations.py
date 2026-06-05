"""Integration tests: migration lifecycle and database constraints."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from filmoteka.domain.catalog.models import Film, Genre, MediaFile, MovieEdition

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Migration lifecycle
# ---------------------------------------------------------------------------

class TestMigrationLifecycle:
    """Verify alembic migrations apply, roll back, and re-apply cleanly."""

    def test_all_migrations_apply(self, alembic_config: Any) -> None:
        """Fresh database reaches the latest revision."""
        from alembic.command import downgrade, upgrade

        # Already at head from conftest, downgrade and re-upgrade
        downgrade(alembic_config, "base")
        upgrade(alembic_config, "head")

    def test_downgrade_roundtrip(self, alembic_config: Any) -> None:
        """upgrade → downgrade -1 → upgrade is reversible."""
        from alembic.command import downgrade, upgrade

        # Downgrade one step from current head
        downgrade(alembic_config, "-1")
        # Re-upgrade
        upgrade(alembic_config, "head")

    def test_tables_exist(self, db_engine: Engine) -> None:
        """All expected tables are present after migration."""
        inspector = inspect(db_engine)
        tables = set(inspector.get_table_names())

        expected = {
            "films",
            "persons",
            "genres",
            "film_genre",
            "film_person",
            "movie_editions",
            "media_files",
            "alembic_version",
        }
        missing = expected - tables
        assert not missing, f"missing tables: {missing}"


# ---------------------------------------------------------------------------
# Constraint enforcement
# ---------------------------------------------------------------------------

class TestForeignKeyConstraints:
    """ON DELETE CASCADE and referential integrity."""

    def test_cascade_delete_film(self, db_session: Session) -> None:
        """Deleting a film cascades to editions, media files, and relations.

        Uses raw SQL to avoid SQLAlchemy ORM relationship-sync overriding
        NOT NULL FK columns during intermediate flushes.
        """
        # Arrange: insert rows via raw SQL
        now = "2026-01-01 00:00:00"
        film_id: int = db_session.execute(
            text(
                "INSERT INTO films (title, year, created_at, updated_at) "
                "VALUES ('Test Film', 2020, :now, :now) RETURNING id"
            ),
            {"now": now},
        ).scalar_one()

        edition_id: int = db_session.execute(
            text(
                "INSERT INTO movie_editions (film_id, quality, created_at) "
                "VALUES (:fid, '1080p', :now) RETURNING id"
            ),
            {"fid": film_id, "now": now},
        ).scalar_one()

        file_id: int = db_session.execute(
            text(
                "INSERT INTO media_files (edition_id, file_path, duration_secs, created_at) "
                "VALUES (:eid, '/tmp/test_cascade.mp4', 120.0, :now) RETURNING id"
            ),
            {"eid": edition_id, "now": now},
        ).scalar_one()

        genre_id: int = db_session.execute(
            text(
                "INSERT INTO genres (name, slug) "
                "VALUES ('Sci-Fi', 'sci-fi') RETURNING id"
            )
        ).scalar_one()

        person_id: int = db_session.execute(
            text(
                "INSERT INTO persons (name, created_at) "
                "VALUES ('Director', :now) RETURNING id"
            ),
            {"now": now},
        ).scalar_one()

        db_session.execute(
            text("INSERT INTO film_genre (film_id, genre_id) VALUES (:fid, :gid)"),
            {"fid": film_id, "gid": genre_id},
        )
        db_session.execute(
            text(
                "INSERT INTO film_person (film_id, person_id, role) "
                "VALUES (:fid, :pid, 'director')"
            ),
            {"fid": film_id, "pid": person_id},
        )
        db_session.flush()

        # Act: delete the film
        db_session.execute(text("DELETE FROM films WHERE id = :fid"), {"fid": film_id})
        db_session.flush()

        # Assert: cascade deleted edition, media file, and relations
        result = db_session.execute(
            text("SELECT id FROM movie_editions WHERE id = :eid"), {"eid": edition_id}
        )
        assert result.fetchone() is None, "edition should be cascade-deleted"

        result = db_session.execute(
            text("SELECT id FROM media_files WHERE id = :fid"), {"fid": file_id}
        )
        assert result.fetchone() is None, "media file should be cascade-deleted"

        result = db_session.execute(
            text("SELECT film_id FROM film_person WHERE film_id = :fid"), {"fid": film_id}
        )
        assert result.fetchone() is None, "film_person should be cascade-deleted"

        result = db_session.execute(
            text("SELECT film_id FROM film_genre WHERE film_id = :fid"), {"fid": film_id}
        )
        assert result.fetchone() is None, "film_genre should be cascade-deleted"


class TestUniqueConstraints:
    """UNIQUE and UNIQUE COMPOSITE constraints are enforced."""

    def test_unique_file_path(self, db_session: Session) -> None:
        """Duplicating a media file path raises IntegrityError."""
        film = Film(title="Dup Path Film")
        edition = MovieEdition(film=film)
        db_session.add_all([film, edition])
        db_session.flush()

        db_session.add(
            MediaFile(edition_id=edition.id, file_path="/dup/path.mp4")
        )
        db_session.flush()

        with pytest.raises(IntegrityError):
            db_session.add(
                MediaFile(edition_id=edition.id, file_path="/dup/path.mp4")
            )
            db_session.flush()

    def test_unique_genre_slug(self, db_session: Session) -> None:
        """Duplicating a genre slug raises IntegrityError."""
        db_session.add(Genre(name="Action", slug="action"))
        db_session.flush()

        with pytest.raises(IntegrityError):
            db_session.add(Genre(name="Action Again", slug="action"))
            db_session.flush()
