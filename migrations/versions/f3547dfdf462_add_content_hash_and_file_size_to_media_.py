"""Add content_hash and file_size to media_files

Revision ID: f3547dfdf462
Revises: 3a4b5c6d7e8f
Create Date: 2026-06-14 10:16:45.835370
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3547dfdf462"
down_revision: Union[str, None] = "3a4b5c6d7e8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("films", "kinopoisk_url")


def downgrade() -> None:
    op.add_column(
        "films",
        sa.Column("kinopoisk_url", sa.VARCHAR(length=1024), nullable=True),
    )
