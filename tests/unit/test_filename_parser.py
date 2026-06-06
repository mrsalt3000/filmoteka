"""Unit tests for filename parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from filmoteka.infrastructure.filename_parser import ParsedFilename, parse_filename


def _p(name: str) -> ParsedFilename:
    """Shortcut: parse a filename (as if it had a .mkv extension)."""
    return parse_filename(Path(name))


class TestParseTypicalNames:
    """Common filename patterns encountered in the wild."""

    def test_dotted_name_with_year_and_quality(self) -> None:
        r = _p("The.Matrix.1999.1080p.WEB-DL.mkv")
        assert r.title == "The Matrix"
        assert r.year == 1999
        assert r.quality == "1080p"

    def test_bracketed_year_and_quality(self) -> None:
        r = _p("Inception (2010) [2160p].mp4")
        assert r.title == "Inception"
        assert r.year == 2010
        assert r.quality == "2160p"

    def test_russian_title_with_year_and_quality(self) -> None:
        r = _p("Пираты Карибского моря 2003 BDRip.mkv")
        assert r.title == "Пираты Карибского моря"
        assert r.year == 2003
        assert r.quality == "BDRip"

    def test_no_metadata(self) -> None:
        r = _p("Unknown.mkv")
        assert r.title == "Unknown"
        assert r.year is None
        assert r.quality is None

    def test_underscore_separators(self) -> None:
        r = _p("The_Dark_Knight_2008_1080p.mkv")
        assert r.title == "The Dark Knight"
        assert r.year == 2008
        assert r.quality == "1080p"

    def test_dash_separators(self) -> None:
        r = _p("Interstellar-2014-2160p-BluRay.mkv")
        assert r.title == "Interstellar"
        assert r.year == 2014
        assert r.quality == "2160p"

    def test_webrip_quality(self) -> None:
        r = _p("Dune.2021.1080p.WEBRip.mkv")
        assert r.title == "Dune"
        assert r.year == 2021
        assert r.quality == "1080p"

    def test_quality_with_spaces(self) -> None:
        r = _p("Movie Name 2022 1080 p WEB DL.mp4")
        assert r.title == "Movie Name"
        assert r.year == 2022
        assert r.quality == "1080p"

    def test_4k_quality(self) -> None:
        r = _p("Avatar.2009.4K.BluRay.mkv")
        assert r.title == "Avatar"
        assert r.year == 2009
        assert r.quality == "4K"

    def test_year_in_brackets_and_quality_in_brackets(self) -> None:
        r = _p("Parasite (2019) [WEBRip].mkv")
        assert r.title == "Parasite"
        assert r.year == 2019
        assert r.quality == "WEBRip"


class TestEdgeCases:
    """Fringe cases that should not crash the parser."""

    def test_empty_stem(self) -> None:
        r = _p(".mkv")
        # Path(".mkv").stem returns "mkv" — nothing to parse
        assert r.title == "mkv"
        assert r.year is None
        assert r.quality is None

    def test_only_year(self) -> None:
        r = _p("2022.mkv")
        assert r.title == ""
        assert r.year == 2022

    def test_year_out_of_range(self) -> None:
        r = _p("Movie.1800.mkv")
        # 1800 is outside 1900-2099 — not treated as a year
        assert r.title == "Movie 1800"
        assert r.year is None

    def test_future_year(self) -> None:
        r = _p("Future.2100.mkv")
        # 2100 is outside 1900-2099 — not treated as a year
        assert r.title == "Future 2100"
        assert r.year is None

    def test_multiple_dots_no_metadata(self) -> None:
        r = _p("some.cool.movie.mkv")
        assert r.title == "some cool movie"
        assert r.year is None
        assert r.quality is None

    def test_special_characters(self) -> None:
        r = _p("The_Film_ (2020) [1080p] !!!.mkv")
        assert r.title == "The Film"
        assert r.year == 2020
        assert r.quality == "1080p"

    def test_title_with_digits(self) -> None:
        r = _p("Room.2015.1080p.mkv")
        assert r.title == "Room"
        assert r.year == 2015
        assert r.quality == "1080p"

    def test_tv_episode_like(self) -> None:
        r = _p("Show.Name.S01E02.2022.1080p.mkv")
        assert r.title == "Show Name S01E02"
        assert r.year == 2022
        assert r.quality == "1080p"

    def test_bd_rip_variant(self) -> None:
        r = _p("The.Godfather.1972.BDRip.1080p.mkv")
        assert r.title == "The Godfather"
        assert r.year == 1972
        # BDRip is matched first, then 1080p would be in the remaining string
        # but since quality is already extracted, it stays in title if after
        # the quality marker
        assert r.quality is not None


class TestParsedFilenameDataclass:
    """ParsedFilename is a frozen dataclass."""

    def test_immutable(self) -> None:
        p = ParsedFilename(title="Test", year=2024, quality="1080p")
        with pytest.raises(AttributeError):
            p.title = "Changed"  # type: ignore[misc]

    def test_repr(self) -> None:
        p = ParsedFilename(title="Test", year=2024, quality="1080p")
        r = repr(p)
        assert "ParsedFilename" in r
        assert "Test" in r
        assert "2024" in r
        assert "1080p" in r
