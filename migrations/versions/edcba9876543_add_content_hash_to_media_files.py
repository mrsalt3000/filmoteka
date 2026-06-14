"""Add content_hash to media_files

Revision ID: edcba9876543
Revises: f3547dfdf462
Create Date: 2026-06-14 10:25:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "edcba9876543"
down_revision: Union[str, None] = "f3547dfdf462"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "media_files",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        op.f("ix_media_files_content_hash"),
        "media_files",
        ["content_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_media_files_content_hash"), table_name="media_files")
    op.drop_column("media_files", "content_hash")
