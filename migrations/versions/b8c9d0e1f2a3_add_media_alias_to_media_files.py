"""add media_alias column to media_files

Revision ID: b8c9d0e1f2a3
Revises: a97c8e6f5d4a
Create Date: 2026-06-12 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, None] = 'a97c8e6f5d4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add column as nullable
    op.add_column(
        'media_files',
        sa.Column('media_alias', sa.String(512), nullable=True),
    )

    # 2. Backfill: extract filename (last path component) as default alias
    conn = op.get_bind()
    if conn.dialect.name == 'postgresql':
        conn.execute(
            sa.text(
                "UPDATE media_files "
                "SET media_alias = reverse(split_part(reverse(file_path), '/', 1)) "
                "WHERE media_alias IS NULL"
            )
        )


def downgrade() -> None:
    op.drop_column('media_files', 'media_alias')
