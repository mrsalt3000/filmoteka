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
        p = ParsedFilename(
            title="Test", year=2024, quality="1080p",
            language=None, edition_type=None,
        )
        with pytest.raises(AttributeError):
            p.title = "Changed"  # type: ignore[misc]

    def test_repr(self) -> None:
        p = ParsedFilename(
            title="Test", year=2024, quality="1080p",
            language="RUS", edition_type="Extended.Cut",
        )
        r = repr(p)
        assert "ParsedFilename" in r
        assert "Test" in r
        assert "2024" in r
        assert "1080p" in r
        assert "RUS" in r
        assert "Extended.Cut" in r


class TestLanguageExtraction:
    """Language markers in filenames."""

    def test_russian_language(self) -> None:
        r = _p("The.Matrix.1999.1080p.RUS.mkv")
        assert r.title == "The Matrix"
        assert r.language == "RUS"

    def test_original_language(self) -> None:
        r = _p("The.Matrix.1999.1080p.Original.mkv")
        assert r.title == "The Matrix"
        assert r.language == "Original"

    def test_dubbed(self) -> None:
        r = _p("The.Matrix.1999.1080p.DUB.mkv")
        assert r.title == "The Matrix"
        assert r.language == "DUB"

    def test_english_audio(self) -> None:
        r = _p("The.Matrix.1999.1080p.ENG.mkv")
        assert r.title == "The Matrix"
        assert r.language == "ENG"

    def test_multi_language(self) -> None:
        r = _p("The.Matrix.1999.1080p.Multi.mkv")
        assert r.title == "The Matrix"
        assert r.language == "Multi"

    def test_no_language_marker(self) -> None:
        r = _p("The.Matrix.1999.1080p.mkv")
        assert r.language is None

    def test_language_spanish(self) -> None:
        r = _p("The.Matrix.1999.1080p.SPA.mkv")
        assert r.title == "The Matrix"
        assert r.language == "SPA"

    def test_subtitles_marker(self) -> None:
        r = _p("The.Matrix.1999.1080p.SUB.mkv")
        assert r.title == "The Matrix"
        assert r.language == "SUB"

    def test_rus_not_confused_with_filename_part(self) -> None:
        r = _p("Отель.RUS.2023.1080p.mkv")
        # "RUS" after a dot — should be treated as a language marker
        assert r.language == "RUS"
        assert r.title == "Отель"
        assert r.year == 2023


class TestEditionExtraction:
    """Edition markers in filenames."""

    def test_directors_cut(self) -> None:
        r = _p("Blade.Runner.1982.Directors.Cut.1080p.mkv")
        assert r.title == "Blade Runner"
        assert r.edition_type == "Directors.Cut"

    def test_extended_cut(self) -> None:
        r = _p("Lord.of.the.Rings.2001.Extended.Cut.1080p.mkv")
        assert r.title == "Lord of the Rings"
        assert r.edition_type == "Extended.Cut"

    def test_theatrical(self) -> None:
        r = _p("Avatar.2009.Theatrical.1080p.mkv")
        assert r.title == "Avatar"
        assert r.edition_type == "Theatrical"

    def test_unrated(self) -> None:
        r = _p("Movie.2022.1080p.Unrated.mkv")
        assert r.title == "Movie"
        assert r.edition_type == "Unrated"

    def test_no_edition(self) -> None:
        r = _p("The.Matrix.1999.1080p.mkv")
        assert r.edition_type is None

    def test_remastered(self) -> None:
        r = _p("Toy.Story.1995.Remastered.1080p.mkv")
        assert r.title == "Toy Story"
        assert r.edition_type == "Remastered"
