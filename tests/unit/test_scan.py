"""Unit tests for the scan_downloads helper ``_collect_files`` and models."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from filmoteka.domain.importing.models import (
    CANDIDATE_ERROR,
    CANDIDATE_PENDING,
    CANDIDATE_PROBED,
    ImportCandidate,
    ImportRun,
)
from filmoteka.domain.importing.scan import _collect_files, probe_candidates
from filmoteka.infrastructure.media_probe import MediaProbeResult


class TestImportCandidateModel:
    """ImportCandidate model — construction and defaults (pure, no DB)."""

    def test_create_candidate(self) -> None:
        candidate = ImportCandidate(
            import_run_id=1,
            file_path="/path/to/film.mkv",
            size=1_234_567_890,
            status=CANDIDATE_PENDING,
        )
        assert candidate.import_run_id == 1
        assert candidate.file_path == "/path/to/film.mkv"
        assert candidate.size == 1_234_567_890
        assert candidate.status == CANDIDATE_PENDING
        assert candidate.id is None  # not persisted

    def test_candidate_repr(self) -> None:
        candidate = ImportCandidate(
            import_run_id=42,
            file_path="/path/to/film.mkv",
            size=1000,
            status=CANDIDATE_PENDING,
        )
        r = repr(candidate)
        assert "ImportCandidate" in r
        assert "42" in r
        assert "pending" in r
        assert "/path/to/film.mkv" in r

    def test_candidate_custom_status(self) -> None:
        candidate = ImportCandidate(
            import_run_id=1,
            file_path="/a.mkv",
            size=100,
            status="imported",
        )
        assert candidate.status == "imported"

    def test_importrun_candidates_relationship(self) -> None:
        run = ImportRun(status="running")
        run.candidates = [
            ImportCandidate(file_path="/a.mkv", size=100, import_run_id=0),
            ImportCandidate(file_path="/b.mp4", size=200, import_run_id=0),
        ]
        assert len(run.candidates) == 2
        assert run.candidates[0].file_path == "/a.mkv"


class TestCollectFiles:
    """_collect_files — file discovery by extension (pure, no DB)."""

    def test_finds_matching_files(self, tmp_path: Path) -> None:
        (tmp_path / "movie1.mp4").touch()
        (tmp_path / "movie2.mkv").touch()
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.avi").touch()

        files = _collect_files(tmp_path, [".mp4", ".mkv", ".avi"])
        assert len(files) == 3
        assert all(f.suffix in {".mp4", ".mkv", ".avi"} for f in files)

    def test_ignores_wrong_extensions(self, tmp_path: Path) -> None:
        (tmp_path / "readme.txt").touch()
        (tmp_path / "poster.jpg").touch()
        (tmp_path / "movie.mp4").touch()

        files = _collect_files(tmp_path, [".mp4"])
        assert files == [tmp_path / "movie.mp4"]

    def test_ignores_directories(self, tmp_path: Path) -> None:
        (tmp_path / "movie.mp4").touch()
        (tmp_path / "a_dir").mkdir()

        files = _collect_files(tmp_path, [".mp4", ".mkv"])
        assert files == [tmp_path / "movie.mp4"]

    def test_extension_case_insensitive(self, tmp_path: Path) -> None:
        (tmp_path / "Movie.MP4").touch()
        (tmp_path / "movie.mkv").touch()

        files = _collect_files(tmp_path, [".mp4"])
        assert files == [tmp_path / "Movie.MP4"]

    def test_empty_directory(self, tmp_path: Path) -> None:
        files = _collect_files(tmp_path, [".mp4"])
        assert files == []

    def test_non_existent_directory(self) -> None:
        files = _collect_files(Path("/nonexistent/path"), [".mp4"])
        assert files == []


class TestProbeCandidates:
    """probe_candidates — status filtering and mixed results (mocked ffprobe)."""

    def _make_candidate(
        self, file_path: str = "/tmp/film.mkv", status: str = CANDIDATE_PENDING
    ) -> ImportCandidate:
        return ImportCandidate(
            import_run_id=1,
            file_path=file_path,
            size=1000,
            status=status,
        )

    def test_skips_non_pending(self) -> None:
        candidates = [
            self._make_candidate(status=CANDIDATE_PROBED),
            self._make_candidate(status=CANDIDATE_ERROR),
            self._make_candidate(status=CANDIDATE_PENDING),
        ]
        db = MagicMock()

        with patch(
            "filmoteka.domain.importing.scan.probe_media",
            return_value=MediaProbeResult(
                duration_secs=10.0,
                width=1920,
                height=1080,
                codec="h264",
                audio_codec="aac",
                audio_count=1,
                subtitle_count=0,
            ),
        ):
            probe_candidates(candidates, db)

        # Only the pending one should have been probed
        assert candidates[0].status == CANDIDATE_PROBED  # unchanged
        assert candidates[1].status == CANDIDATE_ERROR  # unchanged
        assert candidates[2].status == CANDIDATE_PROBED  # changed
        assert candidates[2].probed_at is not None
        assert candidates[2].codec == "h264"

    def test_mixed_success_and_failure(self) -> None:
        ok1 = self._make_candidate(file_path="/tmp/ok.mkv", status=CANDIDATE_PENDING)
        fail = self._make_candidate(file_path="/tmp/fail.mkv", status=CANDIDATE_PENDING)
        ok2 = self._make_candidate(file_path="/tmp/ok2.mkv", status=CANDIDATE_PENDING)

        db = MagicMock()

        from filmoteka.infrastructure.media_probe import MediaProbeError

        def fake_probe(path: Path) -> MediaProbeResult:
            if "fail" in path.name:
                raise MediaProbeError("broken")
            return MediaProbeResult(
                duration_secs=5.0,
                width=640,
                height=480,
                codec="hevc",
                audio_codec="aac",
                audio_count=2,
                subtitle_count=1,
            )

        with patch(
            "filmoteka.domain.importing.scan.probe_media",
            side_effect=fake_probe,
        ):
            probe_candidates([ok1, fail, ok2], db)

        assert ok1.status == CANDIDATE_PROBED
        assert ok1.codec == "hevc"
        assert fail.status == CANDIDATE_ERROR
        assert fail.probed_at is None
        assert ok2.status == CANDIDATE_PROBED
        assert ok2.codec == "hevc"
