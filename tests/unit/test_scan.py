"""Unit tests for the scan_downloads helper ``_collect_files``."""

from __future__ import annotations

from pathlib import Path

from filmoteka.domain.importing.scan import _collect_files


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
