"""Integration tests for the import pipeline."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from filmoteka.domain.importing.models import (
    CANDIDATE_ERROR,
    CANDIDATE_PROBED,
    ImportCandidate,
    ImportRun,
)
from filmoteka.domain.importing.scan import probe_candidates, scan_downloads
from filmoteka.infrastructure.library_config import LibraryConfig

pytestmark = pytest.mark.integration


def _make_config(downloads_root: Path) -> LibraryConfig:
    return LibraryConfig.model_validate({
        "paths": {"downloads_root": str(downloads_root), "target_root": "/media/library"},
        "import": {"extensions": [".mp4", ".mkv"], "max_file_size_gb": 50},
        "organization": "by_year",
    })


def _make_test_video(path: Path) -> None:
    """Generate a tiny valid MP4 with one video + one audio stream."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", "testsrc=duration=1:size=32x24:rate=1",
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono",
            "-shortest",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )


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


class TestProbeCandidates:
    """probe_candidates — end-to-end with real DB and real media file."""

    def test_probe_success(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        (tmp_path / "film.mp4").touch()
        config = _make_config(tmp_path)
        run = scan_downloads(config, db_session)
        db_session.refresh(run)

        candidates = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .all()
        )
        assert len(candidates) == 1

        # Replace the empty file with a real video
        _make_test_video(Path(candidates[0].file_path))

        probe_candidates(candidates, db_session)
        db_session.refresh(candidates[0])

        c = candidates[0]
        assert c.status == CANDIDATE_PROBED
        assert c.probed_at is not None
        assert c.codec is not None
        assert c.width is not None and c.width > 0
        assert c.height is not None and c.height > 0
        assert c.audio_codec is not None

    def test_probe_missing_file(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        (tmp_path / "film.mp4").touch()
        config = _make_config(tmp_path)
        run = scan_downloads(config, db_session)
        db_session.refresh(run)

        candidates = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .all()
        )

        # Delete the file so probe fails
        Path(candidates[0].file_path).unlink()

        probe_candidates(candidates, db_session)
        db_session.refresh(candidates[0])

        assert candidates[0].status == CANDIDATE_ERROR
        assert candidates[0].probed_at is None

    def test_probe_skips_already_probed(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        (tmp_path / "film.mp4").touch()
        config = _make_config(tmp_path)
        run = scan_downloads(config, db_session)
        db_session.refresh(run)

        candidates = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .all()
        )
        _make_test_video(Path(candidates[0].file_path))

        # First probe — should succeed
        probe_candidates(candidates, db_session)
        db_session.refresh(candidates[0])
        assert candidates[0].status == CANDIDATE_PROBED
        first_probed_at = candidates[0].probed_at

        # Second probe — should skip because status is already probed
        probe_candidates(candidates, db_session)
        db_session.refresh(candidates[0])
        assert candidates[0].probed_at == first_probed_at


class TestCandidateCascadeDelete:
    """Cascade delete of ImportCandidate when ImportRun is removed."""

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
