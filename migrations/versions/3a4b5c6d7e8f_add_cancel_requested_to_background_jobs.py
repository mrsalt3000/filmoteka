"""add cancel_requested to background_jobs

Revision ID: 3a4b5c6d7e8f
Revises: 29b98031c35f
Create Date: 2026-06-13 17:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3a4b5c6d7e8f"
down_revision: Union[str, None] = "29b98031c35f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "background_jobs",
        sa.Column(
            "cancel_requested",
            sa.Boolean(),
            server_default=sa.text("FALSE"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("background_jobs", "cancel_requested")
