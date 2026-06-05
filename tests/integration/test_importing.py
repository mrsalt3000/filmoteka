"""Integration tests for the import pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from filmoteka.domain.importing.models import ImportRun
from filmoteka.domain.importing.scan import scan_downloads
from filmoteka.infrastructure.library_config import LibraryConfig

pytestmark = pytest.mark.integration


def _make_config(downloads_root: Path) -> LibraryConfig:
    return LibraryConfig.model_validate({
        "paths": {"downloads_root": str(downloads_root), "target_root": "/media/library"},
        "import": {"extensions": [".mp4", ".mkv"], "max_file_size_gb": 50},
        "organization": "by_year",
    })


class TestScanDownloads:
    """scan_downloads — end-to-end with real DB."""

    def test_scan_creates_import_run(self, db_session: Session, tmp_path: Path) -> None:
        (tmp_path / "film.mp4").touch()
        (tmp_path / "series.mkv").touch()

        config = _make_config(tmp_path)
        run = scan_downloads(config, db_session)

        assert isinstance(run, ImportRun)
        assert run.id is not None
        assert run.status == "completed"
        assert run.file_count == 2
        assert run.finished_at is not None

    def test_scan_no_files(self, db_session: Session, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        run = scan_downloads(config, db_session)
        assert run.file_count == 0
        assert run.status == "completed"

    def test_scan_nonexistent_directory(
        self, db_session: Session
    ) -> None:
        config = _make_config(Path("/does/not/exist"))
        with pytest.raises(NotADirectoryError):
            scan_downloads(config, db_session)
