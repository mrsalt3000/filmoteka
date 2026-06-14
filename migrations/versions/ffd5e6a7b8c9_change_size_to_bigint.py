"""change size columns to BigInteger for large files

Revision ID: ffd5e6a7b8c9
Revises: a1b2c3d4e5f6
Create Date: 2026-06-06 23:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ffd5e6a7b8c9'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # import_candidates.size — files > 2.1 GB overflow Integer
    op.alter_column(
        "import_candidates", "size",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        nullable=False,
    )
    # media_files.file_size — same issue
    op.alter_column(
        "media_files", "file_size",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "import_candidates", "size",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        nullable=False,
    )
    op.alter_column(
        "media_files", "file_size",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        nullable=True,
    )
