"""Unit tests for the scan_downloads helper ``_collect_files`` and models."""

from __future__ import annotations

from pathlib import Path

from filmoteka.domain.importing.models import (
    CANDIDATE_PENDING,
    ImportCandidate,
    ImportRun,
)
from filmoteka.domain.importing.scan import _collect_files


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
