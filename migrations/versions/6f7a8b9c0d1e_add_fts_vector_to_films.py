"""add fts_vector column and GIN index for full-text search

Revision ID: 6f7a8b9c0d1e
Revises: 48634499438a
Create Date: 2026-06-17 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6f7a8b9c0d1e'
down_revision: Union[str, None] = '48634499438a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the tsvector column
    op.add_column(
        'films',
        sa.Column('fts_vector', postgresql.TSVECTOR, nullable=True),
    )

    # Backfill for existing films — includes title, description, episode_title,
    # genre names (via film_genre → genres), and person names (via film_person → persons)
    op.execute("""
        UPDATE films SET fts_vector = to_tsvector('russian',
            coalesce(title, '') || ' ' ||
            coalesce(description, '') || ' ' ||
            coalesce(episode_title, '') || ' ' ||
            coalesce(
                (SELECT string_agg(g.name, ' ')
                 FROM film_genre fg
                 JOIN genres g ON g.id = fg.genre_id
                 WHERE fg.film_id = films.id),
                ''
            ) || ' ' ||
            coalesce(
                (SELECT string_agg(p.name, ' ')
                 FROM film_person fp
                 JOIN persons p ON p.id = fp.person_id
                 WHERE fp.film_id = films.id),
                ''
            )
        )
    """)

    # GIN index for fast @@ queries
    op.create_index('ix_films_fts_vector', 'films', ['fts_vector'], postgres_using='gin')


def downgrade() -> None:
    op.drop_index('ix_films_fts_vector')
    op.drop_column('films', 'fts_vector')
