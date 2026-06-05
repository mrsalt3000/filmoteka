"""Smoke tests for database engine and Alembic configuration."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config


class TestEngineImport:
    """Engine and session factory import and inspect."""

    def test_engine_import(self) -> None:
        from filmoteka.infrastructure.database import engine

        assert engine is not None
        assert engine.url.render_as_string(hide_password=False).startswith(
            "postgresql+psycopg://"
        )

    def test_session_local_import(self) -> None:
        from filmoteka.infrastructure.database import SessionLocal

        assert SessionLocal is not None

    def test_base_import(self) -> None:
        from filmoteka.infrastructure.database import Base

        assert Base is not None
        assert hasattr(Base, "metadata")

    def test_engine_dialect(self) -> None:
        from filmoteka.infrastructure.database import engine

        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"

    def test_get_db_yields_session(self) -> None:
        from filmoteka.infrastructure.database import get_db

        gen = get_db()
        session = next(gen)
        assert session is not None
        session.close()
        with pytest.raises(StopIteration):
            next(gen)


class TestAlembicConfig:
    """Alembic configuration loads and points to correct location."""

    def test_alembic_config_loads(self) -> None:
        config = Config("alembic.ini")
        assert config.config_file_name is not None
        assert Path(config.config_file_name).exists()

    def test_alembic_script_location(self) -> None:
        config = Config("alembic.ini")
        script_location = config.get_main_option("script_location")
        assert script_location == "migrations"

    def test_alembic_env_exists(self) -> None:
        """Verify migrations/env.py exists and can be parsed."""
        env_path = Path("migrations/env.py")
        assert env_path.exists()
        source = env_path.read_text()
        assert "run_migrations_offline" in source
        assert "run_migrations_online" in source

    def test_alembic_sqlalchemy_url(self) -> None:
        from filmoteka.infrastructure.settings import settings

        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", settings.database_url)
        url = config.get_main_option("sqlalchemy.url")
        assert url == settings.database_url

    def test_migration_chain_has_single_head_and_base(self) -> None:
        """Verify the migration chain is linear: 1 base → 1 head."""
        from alembic.script import ScriptDirectory

        config = Config("alembic.ini")
        script = ScriptDirectory.from_config(config)
        heads = script.get_heads()
        bases = script.get_bases()

        assert len(heads) == 1, "expected exactly one head migration"
        assert len(bases) == 1, "expected exactly one base migration"

    def test_migration_files_are_loadable(self) -> None:
        """Verify all migration .py files can be compiled (syntax check)."""
        import ast

        migration_dir = Path("migrations/versions")
        py_files = sorted(migration_dir.glob("*.py"))
        assert len(py_files) >= 2

        for path in py_files:
            source = path.read_text()
            ast.parse(source)  # raises SyntaxError if invalid

