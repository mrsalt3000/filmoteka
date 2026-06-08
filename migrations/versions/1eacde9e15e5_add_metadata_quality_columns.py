"""add metadata quality columns to films

Revision ID: 1eacde9e15e5
Revises: 04572a67037e
Create Date: 2026-06-08 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1eacde9e15e5'
down_revision: Union[str, None] = '04572a67037e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('films', sa.Column('metadata_source', sa.String(length=64), nullable=True))
    op.add_column('films', sa.Column('metadata_confidence', sa.Float(), nullable=True))
    op.add_column('films', sa.Column('metadata_enriched_at', sa.DateTime(), nullable=True))
    op.add_column('films', sa.Column('needs_review', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('films', 'needs_review')
    op.drop_column('films', 'metadata_enriched_at')
    op.drop_column('films', 'metadata_confidence')
    op.drop_column('films', 'metadata_source')
