"""Unit tests for media path re-resolution logic."""

from __future__ import annotations

from pathlib import Path

from filmoteka.api.media import _resolve_media_path


class TestResolveMediaPath:
    """_resolve_media_path — locate files under a library root."""

    def test_exact_filename_match(self, tmp_path: Path) -> None:
        video = tmp_path / "movie.mp4"
        video.write_bytes(b"x")
        result = _resolve_media_path("/old/root/movie.mp4", tmp_path)
        assert result == video

    def test_no_match_returns_none(self, tmp_path: Path) -> None:
        result = _resolve_media_path("/old/root/movie.mp4", tmp_path)
        assert result is None

    def test_empty_stored_path_returns_none(self, tmp_path: Path) -> None:
        result = _resolve_media_path("", tmp_path)
        assert result is None

    def test_invalid_library_root_returns_none(self) -> None:
        result = _resolve_media_path(
            "/old/root/movie.mp4", Path("/nonexistent/dir")
        )
        assert result is None

    def test_multiple_matches_disambiguates_by_relative_path(
        self, tmp_path: Path
    ) -> None:
        """When two files share a basename, the one matching the relative
        path suffix is preferred."""
        sub_a = tmp_path / "Action" / "movie.mp4"
        sub_b = tmp_path / "Drama" / "movie.mp4"
        sub_a.parent.mkdir(parents=True)
        sub_b.parent.mkdir(parents=True)
        sub_a.write_bytes(b"a")
        sub_b.write_bytes(b"b")

        # Stored path was under a different root but same relative layout
        result = _resolve_media_path("/media/library/Action/movie.mp4", tmp_path)
        assert result == sub_a

    def test_multiple_matches_no_relative_clue_returns_none(
        self, tmp_path: Path
    ) -> None:
        """When multiple matches exist and relative path doesn't help,
        return None (ambiguous)."""
        sub1 = tmp_path / "dir1" / "movie.mp4"
        sub2 = tmp_path / "dir2" / "movie.mp4"
        sub1.parent.mkdir(parents=True)
        sub2.parent.mkdir(parents=True)
        sub1.write_bytes(b"a")
        sub2.write_bytes(b"b")

        # Stored path has no useful directory context (just filename)
        result = _resolve_media_path("movie.mp4", tmp_path)
        assert result is None

    def test_match_in_nested_subdirectory(self, tmp_path: Path) -> None:
        video = tmp_path / "2020" / "Action" / "The Matrix (1999).mkv"
        video.parent.mkdir(parents=True)
        video.write_bytes(b"x")
        result = _resolve_media_path(
            "/media/library/The Matrix (1999).mkv", tmp_path
        )
        assert result == video
