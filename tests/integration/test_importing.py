"""Integration tests for the import pipeline."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from filmoteka.domain.importing.models import ImportCandidate, ImportRun
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

    def test_scan_creates_candidates(self, db_session: Session, tmp_path: Path) -> None:
        (tmp_path / "film.mp4").write_bytes(b"x" * 100)
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.mkv").write_bytes(b"x" * 200)

        config = _make_config(tmp_path)
        run = scan_downloads(config, db_session)
        db_session.refresh(run)

        candidates = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .order_by(ImportCandidate.file_path)
            .all()
        )

        assert len(candidates) == 2
        assert candidates[0].file_path == str(tmp_path / "film.mp4")
        assert candidates[0].size == 100
        assert candidates[0].status == "pending"
        assert candidates[1].file_path == str(tmp_path / "subdir" / "nested.mkv")
        assert candidates[1].size == 200
        assert candidates[1].import_run_id == run.id

    def test_candidate_cascade_delete(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        (tmp_path / "film.mp4").touch()
        config = _make_config(tmp_path)
        run = scan_downloads(config, db_session)

        candidates_before = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .count()
        )
        assert candidates_before == 1

        db_session.delete(run)
        db_session.flush()

        candidates_after = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .count()
        )
        assert candidates_after == 0
