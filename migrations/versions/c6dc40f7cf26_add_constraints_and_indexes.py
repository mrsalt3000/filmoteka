"""add constraints and indexes

Revision ID: c6dc40f7cf26
Revises: 487a45a0f362
Create Date: 2026-06-05 19:34:59.903072
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6dc40f7cf26'
down_revision: Union[str, None] = '487a45a0f362'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- film_genre ---
    op.drop_constraint("film_genre_film_id_fkey", "film_genre", type_="foreignkey")
    op.drop_constraint("film_genre_genre_id_fkey", "film_genre", type_="foreignkey")
    op.create_foreign_key(
        "film_genre_film_id_fkey", "film_genre", "films",
        ["film_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "film_genre_genre_id_fkey", "film_genre", "genres",
        ["genre_id"], ["id"], ondelete="CASCADE",
    )

    # --- film_person ---
    op.drop_constraint("film_person_film_id_fkey", "film_person", type_="foreignkey")
    op.drop_constraint("film_person_person_id_fkey", "film_person", type_="foreignkey")
    op.create_foreign_key(
        "film_person_film_id_fkey", "film_person", "films",
        ["film_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "film_person_person_id_fkey", "film_person", "persons",
        ["person_id"], ["id"], ondelete="CASCADE",
    )

    # --- movie_editions ---
    op.drop_constraint(
        "movie_editions_film_id_fkey", "movie_editions", type_="foreignkey"
    )
    op.create_foreign_key(
        "movie_editions_film_id_fkey", "movie_editions", "films",
        ["film_id"], ["id"], ondelete="CASCADE",
    )

    # --- media_files ---
    op.drop_constraint(
        "media_files_edition_id_fkey", "media_files", type_="foreignkey"
    )
    op.create_foreign_key(
        "media_files_edition_id_fkey", "media_files", "movie_editions",
        ["edition_id"], ["id"], ondelete="CASCADE",
    )

    # --- indexes ---
    op.create_index(op.f("ix_films_year"), "films", ["year"], unique=False)
    op.create_index(
        op.f("ix_movie_editions_film_id"), "movie_editions", ["film_id"], unique=False,
    )
    op.create_index(
        op.f("ix_media_files_edition_id"), "media_files", ["edition_id"], unique=False,
    )


def downgrade() -> None:
    # --- indexes ---
    op.drop_index(op.f("ix_media_files_edition_id"), table_name="media_files")
    op.drop_index(op.f("ix_movie_editions_film_id"), table_name="movie_editions")
    op.drop_index(op.f("ix_films_year"), table_name="films")

    # --- media_files ---
    op.drop_constraint(
        "media_files_edition_id_fkey", "media_files", type_="foreignkey",
    )
    op.create_foreign_key(
        "media_files_edition_id_fkey", "media_files", "movie_editions",
        ["edition_id"], ["id"],
    )

    # --- movie_editions ---
    op.drop_constraint(
        "movie_editions_film_id_fkey", "movie_editions", type_="foreignkey",
    )
    op.create_foreign_key(
        "movie_editions_film_id_fkey", "movie_editions", "films",
        ["film_id"], ["id"],
    )

    # --- film_person ---
    op.drop_constraint(
        "film_person_film_id_fkey", "film_person", type_="foreignkey",
    )
    op.drop_constraint(
        "film_person_person_id_fkey", "film_person", type_="foreignkey",
    )
    op.create_foreign_key(
        "film_person_film_id_fkey", "film_person", "films",
        ["film_id"], ["id"],
    )
    op.create_foreign_key(
        "film_person_person_id_fkey", "film_person", "persons",
        ["person_id"], ["id"],
    )

    # --- film_genre ---
    op.drop_constraint(
        "film_genre_genre_id_fkey", "film_genre", type_="foreignkey",
    )
    op.drop_constraint(
        "film_genre_film_id_fkey", "film_genre", type_="foreignkey",
    )
    op.create_foreign_key(
        "film_genre_genre_id_fkey", "film_genre", "genres",
        ["genre_id"], ["id"],
    )
    op.create_foreign_key(
        "film_genre_film_id_fkey", "film_genre", "films",
        ["film_id"], ["id"],
    )
