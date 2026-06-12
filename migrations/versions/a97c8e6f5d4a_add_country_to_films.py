"""add country column to films

Revision ID: a97c8e6f5d4a
Revises: c6678f604e6b
Create Date: 2026-06-12 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a97c8e6f5d4a'
down_revision: Union[str, None] = 'c6678f604e6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('films', sa.Column('country', sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column('films', 'country')
