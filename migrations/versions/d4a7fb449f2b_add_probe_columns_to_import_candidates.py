"""add probe columns to import_candidates

Revision ID: d4a7fb449f2b
Revises: 0322c3ea4703
Create Date: 2026-06-06 15:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4a7fb449f2b'
down_revision: Union[str, None] = '0322c3ea4703'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('import_candidates', sa.Column('probed_at', sa.DateTime(), nullable=True))
    op.add_column('import_candidates', sa.Column('duration_secs', sa.Float(), nullable=True))
    op.add_column('import_candidates', sa.Column('width', sa.Integer(), nullable=True))
    op.add_column('import_candidates', sa.Column('height', sa.Integer(), nullable=True))
    op.add_column('import_candidates', sa.Column('codec', sa.String(length=32), nullable=True))
    op.add_column('import_candidates', sa.Column('audio_codec', sa.String(length=32), nullable=True))
    op.add_column('import_candidates', sa.Column('audio_count', sa.Integer(), nullable=True))
    op.add_column('import_candidates', sa.Column('subtitle_count', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('import_candidates', 'subtitle_count')
    op.drop_column('import_candidates', 'audio_count')
    op.drop_column('import_candidates', 'audio_codec')
    op.drop_column('import_candidates', 'codec')
    op.drop_column('import_candidates', 'height')
    op.drop_column('import_candidates', 'width')
    op.drop_column('import_candidates', 'duration_secs')
    op.drop_column('import_candidates', 'probed_at')
