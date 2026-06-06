"""Unit tests for file layout — target path generation and error handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from filmoteka.domain.importing.layout import (
    LayoutError,
    _sanitise,
    _target_dir,
    _unique_path,
    layout_file,
)
from filmoteka.domain.importing.models import (
    CANDIDATE_ERROR,
    ImportCandidate,
)
from filmoteka.infrastructure.library_config import LibraryConfig


def _make_config(target_root: str = "/media/library") -> LibraryConfig:
    return LibraryConfig.model_validate({
        "paths": {
            "downloads_root": "/media/downloads",
            "target_root": target_root,
        },
        "import": {"extensions": [".mp4"], "max_file_size_gb": 50},
        "organization": "by_year",
    })


def _candidate(
    file_path: str,
    status: str = "pending",
    run_id: int = 1,
) -> ImportCandidate:
    return ImportCandidate(
        import_run_id=run_id,
        file_path=file_path,
        size=1000,
        status=status,
    )


# ---------------------------------------------------------------------------
# _target_dir
# ---------------------------------------------------------------------------


class TestTargetDir:
    """_target_dir — pure path generation from filename."""

    def test_with_year(self) -> None:
        config = _make_config()
        c = _candidate("/downloads/The.Matrix.1999.1080p.mkv")
        result = _target_dir(config, c)
        expected = Path("/media/library/1999/The Matrix (1999)")
        assert result == expected

    def test_without_year(self) -> None:
        config = _make_config()
        c = _candidate("/downloads/Some Movie.mkv")
        result = _target_dir(config, c)
        expected = Path("/media/library/unknown/Some Movie")
        assert result == expected

    def test_russian_title(self) -> None:
        config = _make_config()
        c = _candidate("/downloads/Пираты Карибского моря 2003 BDRip.mkv")
        result = _target_dir(config, c)
        expected = Path("/media/library/2003/Пираты Карибского моря (2003)")
        assert result == expected

    def test_custom_target_root(self) -> None:
        config = _make_config(target_root="/custom/path")
        c = _candidate("/downloads/Inception.2010.1080p.mkv")
        result = _target_dir(config, c)
        expected = Path("/custom/path/2010/Inception (2010)")
        assert result == expected

    def test_empty_title_falls_back_to_unknown(self) -> None:
        config = _make_config()
        c = _candidate("/downloads/.mkv")
        result = _target_dir(config, c)
        assert "unknown" in result.parts


# ---------------------------------------------------------------------------
# _sanitise
# ---------------------------------------------------------------------------


class TestSanitise:
    def test_removes_path_separators(self) -> None:
        assert _sanitise("Movie/Name: Test") == "MovieName Test"

    def test_allows_normal_chars(self) -> None:
        assert _sanitise("The Matrix (1999)") == "The Matrix (1999)"

    def test_strips_whitespace(self) -> None:
        assert _sanitise("  Hello  ") == "Hello"

    def test_russian_allowed(self) -> None:
        assert _sanitise("Пираты Карибского моря") == "Пираты Карибского моря"


# ---------------------------------------------------------------------------
# _unique_path
# ---------------------------------------------------------------------------


class TestUniquePath:
    def test_returns_path_when_free(self) -> None:
        p = _unique_path(Path("/tmp/nonexistent.mkv"))
        assert p == Path("/tmp/nonexistent.mkv")

    def test_appends_suffix_when_exists(self, tmp_path: Path) -> None:
        existing = tmp_path / "movie.mkv"
        existing.touch()
        result = _unique_path(existing)
        assert result == tmp_path / "movie (1).mkv"

    def test_increments_counter(self, tmp_path: Path) -> None:
        (tmp_path / "movie.mkv").touch()
        (tmp_path / "movie (1).mkv").touch()
        result = _unique_path(tmp_path / "movie.mkv")
        assert result == tmp_path / "movie (2).mkv"


# ---------------------------------------------------------------------------
# layout_file — error cases
# ---------------------------------------------------------------------------


class TestLayoutFileErrors:
    def test_source_not_found(self) -> None:
        config = _make_config()
        c = _candidate("/nonexistent/file.mkv")
        db = MagicMock()
        with pytest.raises(LayoutError, match="does not exist"):
            layout_file(c, config, db)
        assert c.status == CANDIDATE_ERROR

    def test_move_raises_oserror(self, tmp_path: Path) -> None:
        config = _make_config(target_root=str(tmp_path / "target"))
        source = tmp_path / "source" / "movie.mkv"
        source.parent.mkdir(parents=True)
        source.touch()

        c = _candidate(str(source))
        db = MagicMock()

        # Place a file where the target directory should be, so mkdir/move fails
        target_dir = _target_dir(config, c)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        target_dir.write_text("i am a file, not a directory")

        with pytest.raises(LayoutError, match="Failed to move"):
            layout_file(c, config, db)
        assert c.status == CANDIDATE_ERROR
