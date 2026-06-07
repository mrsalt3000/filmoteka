"""add poster_url and poster_source to films

Revision ID: c1784ebef74d
Revises: ffd5e6a7b8c9
Create Date: 2026-06-07 23:26:28.874626
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c1784ebef74d'
down_revision: Union[str, None] = 'ffd5e6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('films', sa.Column('poster_url', sa.String(length=1024), nullable=True))
    op.add_column('films', sa.Column('poster_source', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('films', 'poster_source')
    op.drop_column('films', 'poster_url')
