"""Unit test conftest — register TSVECTOR -> TEXT compiles for SQLite."""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.compiler import compiles


@compiles(TSVECTOR, "sqlite")
def _compile_tsvector_sqlite(_type_, _compiler, **_kw):
    """Make PostgreSQL TSVECTOR columns work as TEXT on SQLite."""
    return "TEXT"
