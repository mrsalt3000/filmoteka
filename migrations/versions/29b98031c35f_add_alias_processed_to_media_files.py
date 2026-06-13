"""add alias_processed to media_files

Revision ID: 29b98031c35f
Revises: b8c9d0e1f2a3
Create Date: 2026-06-13 16:39:37.445525
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "29b98031c35f"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "media_files",
        sa.Column(
            "alias_processed",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("media_files", "alias_processed")
