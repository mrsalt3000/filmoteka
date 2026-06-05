from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from filmoteka.infrastructure.settings import Settings


class TestAppImports:
    """Smoke tests: application and config modules can be imported."""

    def test_settings_importable(self) -> None:
        from filmoteka.infrastructure.settings import settings  # noqa: PLC0415

        assert settings.version == "0.1.0"

    def test_library_config_importable(self) -> None:
        from filmoteka.infrastructure.library_config import (  # noqa: PLC0415
            LibraryConfig,
            load_library_config,
        )

        assert LibraryConfig is not None
        assert callable(load_library_config)

    def test_app_factory_importable(self) -> None:
        from filmoteka.app import app, create_app  # noqa: PLC0415

        assert app.title == "Filmoteka"
        assert callable(create_app)


class TestConfigLoading:
    """Smoke tests: settings validate correctly."""

    def test_settings_required_fields(self) -> None:
        assert isinstance(Settings.model_fields["database_url"], object)
        assert isinstance(Settings.model_fields["redis_url"], object)
        assert isinstance(Settings.model_fields["secret_key"], object)

    def test_settings_defaults(self) -> None:
        assert Settings.model_fields["version"].default == "0.1.0"
        assert Settings.model_fields["downloads_root"].default == Path(
            "media/downloads"
        )
        assert Settings.model_fields["library_root"].default == Path("media/library")
        assert Settings.model_fields["library_spec_path"].default == Path(
            "specs/library.yaml"
        )

    def test_library_config_loads(self) -> None:
        from filmoteka.infrastructure.library_config import (  # noqa: PLC0415
            load_library_config,
        )

        cfg = load_library_config(Path("specs/library.yaml"))
        assert ".mp4" in cfg.import_.extensions
        assert cfg.organization == "by_year"


class TestBootstrapBreaks:
    """Negative smoke tests: missing env vars break bootstrap."""

    def test_settings_fails_without_required_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.delenv("filmoteka_database_url", raising=False)
        monkeypatch.delenv("filmoteka_redis_url", raising=False)
        monkeypatch.delenv("filmoteka_secret_key", raising=False)
        monkeypatch.delenv("FILMOTEKA_DATABASE_URL", raising=False)
        monkeypatch.delenv("FILMOTEKA_REDIS_URL", raising=False)
        monkeypatch.delenv("FILMOTEKA_SECRET_KEY", raising=False)

        with pytest.raises(ValidationError):
            Settings()
