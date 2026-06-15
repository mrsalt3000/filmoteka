"""Unit tests for external metadata providers — OMDB poster search."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from filmoteka.infrastructure.metadata_providers import (
    CleanedTitle,
    clean_title_for_omdb,
    detect_search_type,
    omdb_search_poster,
    omdb_search_poster_v2,
)

PATCH_TARGET = "filmoteka.infrastructure.metadata_providers.urlopen"


def _mock_response(status: int, body: bytes) -> MagicMock:
    m = MagicMock()
    m.status = status
    m.read.return_value = body
    return m


# ---------------------------------------------------------------------------
# clean_title_for_omdb
# ---------------------------------------------------------------------------


class TestCleanTitleForOmdb:
    """clean_title_for_omdb — strip tech markers, normalise, extract year."""

    def test_removes_tech_markers(self) -> None:
        """HDTVRip, resolution, codec and language markers are stripped."""
        result = clean_title_for_omdb(
            "Брат.1997.WEB-DLRip-AVC_[New-team]_by_AVP_Studio",
        )
        assert result.title == "Брат"
        assert result.year == 1997

    def test_removes_multiple_markers(self) -> None:
        """Multiple tech markers are all stripped."""
        result = clean_title_for_omdb(
            "The.Matrix.1999.1080p.BluRay.x264.DTS.RUS",
        )
        assert result.title == "The Matrix"
        assert result.year == 1999

    def test_removes_broadcast_tails(self) -> None:
        """Fight/broadcast tails like Main Card, Prelims are removed."""
        result = clean_title_for_omdb("UFC 300 Main Card 2024")
        assert "Main Card" not in result.title
        assert "UFC" not in result.title

    def test_removes_bracketed_groups(self) -> None:
        """[group] style markers are removed."""
        result = clean_title_for_omdb("Movie (2020) [BluRay] [New Team]")
        assert result.title == "Movie"
        assert result.year == 2020

    def test_normalises_separators(self) -> None:
        """Dots, underscores and extra spaces become single spaces."""
        result = clean_title_for_omdb("Star.Wars.Episode.IV")
        assert "  " not in result.title
        assert result.title.startswith("Star Wars")

    def test_extracts_year_from_parentheses(self) -> None:
        """Year in (1999) is extracted."""
        result = clean_title_for_omdb("The Lion King (1994)")
        assert result.title == "The Lion King"
        assert result.year == 1994

    def test_extracts_year_standalone(self) -> None:
        """Year as bare digits is extracted."""
        result = clean_title_for_omdb("Inception 2010")
        assert result.title == "Inception"
        assert result.year == 2010

    def test_handles_series_title(self) -> None:
        """Series title with dots and year is cleaned."""
        result = clean_title_for_omdb("The.Mandalorian.2019")
        assert result.title == "The Mandalorian"
        assert result.year == 2019

    def test_clean_title_preserves_cyrillic(self) -> None:
        """Cyrillic titles are preserved correctly."""
        result = clean_title_for_omdb("Брат 2 (2000) HDRip")
        assert result.title == "Брат 2"
        assert result.year == 2000

    def test_normalises_dashes(self) -> None:
        """Em-dash and en-dash become regular dash."""
        result = clean_title_for_omdb("Star Wars — The Force Awakens 2015")
        assert "—" not in result.title
        assert result.year == 2015

    def test_removes_russian_marker(self) -> None:
        """Cyrillic 'PУС' marker is stripped."""
        result = clean_title_for_omdb("Avatar PУС 2009")
        assert "PУС" not in result.title


# ---------------------------------------------------------------------------
# detect_search_type
# ---------------------------------------------------------------------------


class TestDetectSearchType:
    """detect_search_type — heuristic type detection for OMDB."""

    def test_series_when_series_id(self) -> None:
        """series_id is set → type=series."""
        assert detect_search_type("Any Title", series_id=1) == "series"

    def test_series_keyword_in_title(self) -> None:
        """'Season' in title → type=series."""
        assert detect_search_type("Show Season 1", series_id=None) == "series"

    def test_episode_keyword(self) -> None:
        """'Episode' in title → type=series."""
        assert detect_search_type("S01E01 Pilot", series_id=None) == "series"

    def test_movie_by_default(self) -> None:
        """No series indicators → type=movie."""
        assert detect_search_type("The Matrix", series_id=None) == "movie"

    def test_movie_with_year_in_title(self) -> None:
        """Plain movie title → type=movie."""
        assert detect_search_type("Inception 2010", series_id=None) == "movie"


# ---------------------------------------------------------------------------
# omdb_search_poster_v2
# ---------------------------------------------------------------------------


class TestOmdbSearchPosterV2:
    """omdb_search_poster_v2 — type-aware multi-step search."""

    API_KEY = "test_key_v2"

    def test_exact_match_with_type(self) -> None:
        """Exact match with type=series returns poster."""
        body = b"""
        {
            "Title": "The Mandalorian",
            "Year": "2019",
            "Poster": "https://m.media-amazon.com/images/M/series.jpg",
            "Response": "True"
        }
        """
        with patch(PATCH_TARGET, return_value=_mock_response(200, body)):
            result = omdb_search_poster_v2(
                CleanedTitle("The Mandalorian", 2019), self.API_KEY, type_="series",
            )

        assert result is not None
        url, source = result
        assert url == "https://m.media-amazon.com/images/M/series.jpg"
        assert source == "omdb"

    def test_exact_with_type_in_url(self) -> None:
        """type=series is passed in the ?t= URL."""
        body = b'{"Title": "T", "Poster": "http://p.jpg", "Response": "True"}'
        with patch(PATCH_TARGET) as mock_urlopen:
            mock_urlopen.return_value = _mock_response(200, body)
            omdb_search_poster_v2(
                CleanedTitle("The Mandalorian", 2019), self.API_KEY, type_="series",
            )

        call_url = mock_urlopen.call_args[0][0].full_url
        assert "type=series" in call_url
        assert "t=The+Mandalorian" in call_url

    def test_exact_fails_search_succeeds(self) -> None:
        """?t= returns no poster, ?s= finds one."""
        def side_effect(req: Any, **kw: Any) -> MagicMock:
            url = str(getattr(req, "full_url", ""))
            if "?t=" in url or "&t=" in url:
                return _mock_response(200, b"""
                    {"Response": "False", "Error": "Movie not found!"}
                """)
            if "?i=" in url or "&i=" in url:
                return _mock_response(200, b"""
                    {"Title": "Found Movie", "Poster": "http://found.jpg",
                     "Response": "True"}
                """)
            return _mock_response(200, b"""
                {
                    "Search": [
                        {"Title": "Found Movie", "Year": "2020",
                         "Poster": "N/A", "imdbID": "tt9999999"},
                        {"Title": "Wrong Movie", "Year": "2021",
                         "Poster": "N/A", "imdbID": "tt8888888"}
                    ],
                    "totalResults": "2",
                    "Response": "True"
                }
            """)

        with patch(PATCH_TARGET, side_effect=side_effect):
            result = omdb_search_poster_v2(
                CleanedTitle("Found Movie", 2020), self.API_KEY,
            )

        assert result is not None
        url, source = result
        assert url == "http://found.jpg"
        assert source == "omdb"

    def test_search_poster_direct(self) -> None:
        """?s= returns results where best candidate has a poster."""
        body = b"""
        {
            "Search": [
                {"Title": "My Movie", "Year": "2020",
                 "Poster": "https://m.media-amazon.com/images/M/p.jpg",
                 "imdbID": "tt123"},
                {"Title": "Other", "Year": "2021",
                 "Poster": "N/A", "imdbID": "tt456"}
            ],
            "totalResults": "2",
            "Response": "True"
        }
        """
        def side_effect(req: Any, **kw: Any) -> MagicMock:
            url = str(getattr(req, "full_url", ""))
            if "?t=" in url or "&t=" in url:
                return _mock_response(200, b"""
                    {"Response": "False", "Error": "Movie not found!"}
                """)
            return _mock_response(200, body)

        with patch(PATCH_TARGET, side_effect=side_effect):
            result = omdb_search_poster_v2(
                CleanedTitle("My Movie", 2020), self.API_KEY,
            )

        assert result is not None
        url, source = result
        assert url == "https://m.media-amazon.com/images/M/p.jpg"

    def test_imdb_id_fallback(self) -> None:
        """?s= finds candidate with N/A poster, ?i= returns poster."""
        call_log: list[str] = []

        def side_effect(req: Any, **kw: Any) -> MagicMock:
            url = str(getattr(req, "full_url", ""))
            call_log.append(url)
            if "?t=" in url or "&t=" in url:
                return _mock_response(200, b"""
                    {"Response": "False", "Error": "Movie not found!"}
                """)
            if "?i=" in url or "&i=" in url:
                return _mock_response(200, b"""
                    {"Title": "IMDB Movie", "Poster": "http://imdb.jpg",
                     "Response": "True"}
                """)
            return _mock_response(200, b"""
                {
                    "Search": [
                        {"Title": "My Movie", "Year": "2020",
                         "Poster": "N/A", "imdbID": "tt9990000"},
                        {"Title": "Other", "Year": "2021",
                         "Poster": "N/A", "imdbID": "tt9991111"}
                    ],
                    "totalResults": "2",
                    "Response": "True"
                }
            """)

        with patch(PATCH_TARGET, side_effect=side_effect):
            result = omdb_search_poster_v2(
                CleanedTitle("My Movie", 2020), self.API_KEY,
            )

        assert result is not None
        url, source = result
        assert url == "http://imdb.jpg"
        assert source == "omdb"
        # 3 calls: ?t=, ?s=, ?i=
        assert len(call_log) == 3

    def test_double_shot_when_type_none(self) -> None:
        """No type → tries series, then movie, then final fallback."""
        call_log: list[str] = []

        def side_effect(req: Any, **kw: Any) -> MagicMock:
            url = str(getattr(req, "full_url", ""))
            call_log.append(url)
            return _mock_response(200, b"""
                {"Response": "False", "Error": "Not found!"}
            """)

        with patch(PATCH_TARGET, side_effect=side_effect):
            result = omdb_search_poster_v2(
                CleanedTitle("Unknown", 2000), self.API_KEY,
            )

        assert result is None  # nothing found
        # First pass: ?t=, ?s= (no type)
        # Then type=series: ?t=+type=series, ?s=+type=series
        # Then type=movie: ?t=+type=movie, ?s=+type=movie
        # Final fallback: ?s= (no year, no type)
        assert len(call_log) >= 6

    def test_type_is_passed_in_url(self) -> None:
        """When type_=series, the URL contains type=series."""
        body = b'{"Title": "T", "Poster": "http://p.jpg", "Response": "True"}'
        with patch(PATCH_TARGET) as mock_urlopen:
            mock_urlopen.return_value = _mock_response(200, body)
            omdb_search_poster_v2(
                CleanedTitle("My Show", 2021), self.API_KEY, type_="series",
            )

        call_url = mock_urlopen.call_args[0][0].full_url
        assert "type=series" in call_url

    def test_not_found_returns_none(self) -> None:
        """No poster found anywhere returns None."""
        body = b'{"Response": "False", "Error": "Movie not found!"}'
        with patch(PATCH_TARGET, return_value=_mock_response(200, body)):
            result = omdb_search_poster_v2(
                CleanedTitle("Absent", 1999), self.API_KEY,
            )

        assert result is None


# ---------------------------------------------------------------------------
# omdb_search_poster (legacy) — must still work
# ---------------------------------------------------------------------------


class TestOmdbSearchPoster:
    """omdb_search_poster — poster URL lookup via OMDB API."""

    API_KEY = "test_key_123"

    def test_found_exact_with_year(self) -> None:
        """Happy path — exact match via ?t, poster found, year matches."""
        body = b"""
        {
            "Title": "The Matrix",
            "Year": "1999",
            "Poster": "https://m.media-amazon.com/images/M/abc123.jpg",
            "Response": "True"
        }
        """
        with patch(PATCH_TARGET, return_value=_mock_response(200, body)):
            result = omdb_search_poster("The Matrix", 1999, self.API_KEY)

        assert result is not None
        url, source = result
        assert url == "https://m.media-amazon.com/images/M/abc123.jpg"
        assert source == "omdb"

    def test_found_exact_without_year(self) -> None:
        """Exact match when year is None."""
        body = b"""
        {
            "Title": "Some Movie",
            "Poster": "https://m.media-amazon.com/images/M/xyz789.jpg",
            "Response": "True"
        }
        """
        with patch(PATCH_TARGET, return_value=_mock_response(200, body)):
            result = omdb_search_poster("Some Movie", None, self.API_KEY)

        assert result is not None
        url, source = result
        assert url == "https://m.media-amazon.com/images/M/xyz789.jpg"
        assert source == "omdb"

    def test_exact_not_found_fallback_to_search(self) -> None:
        """Exact match returns N/A, falls back to ?s search."""
        def side_effect(req: Any, **kw: Any) -> MagicMock:
            url = str(getattr(req, "full_url", ""))
            if "?t=" in url or "&t=" in url:
                return _mock_response(200, b"""
                    {"Response": "False", "Error": "Movie not found!"}
                """)
            return _mock_response(200, b"""
                {
                    "Search": [
                        {"Title": "Test Movie", "Year": "2020",
                         "Poster": "https://m.media-amazon.com/images/M/poster.jpg",
                         "imdbID": "tt1234567"},
                        {"Title": "Test Movie 2", "Year": "2021",
                         "Poster": "N/A", "imdbID": "tt7654321"}
                    ],
                    "totalResults": "2",
                    "Response": "True"
                }
            """)

        with patch(PATCH_TARGET, side_effect=side_effect):
            result = omdb_search_poster("Test Movie", 2020, self.API_KEY)

        assert result is not None
        url, source = result
        assert url == "https://m.media-amazon.com/images/M/poster.jpg"
        assert source == "omdb"

    def test_both_levels_na(self) -> None:
        """Both exact and search return N/A poster — returns None."""
        def side_effect(req: Any, **kw: Any) -> MagicMock:
            url = str(getattr(req, "full_url", ""))
            if "?t=" in url or "&t=" in url:
                return _mock_response(200, b"""
                    {"Title": "No Poster", "Poster": "N/A", "Response": "True"}
                """)
            return _mock_response(200, b"""
                {"Search": [], "totalResults": "0", "Response": "True"}
            """)

        with patch(PATCH_TARGET, side_effect=side_effect):
            result = omdb_search_poster("No Poster", 2000, self.API_KEY)

        assert result is None

    def test_no_results_at_all(self) -> None:
        """Exact not found, search returns empty — None."""
        def side_effect(req: Any, **kw: Any) -> MagicMock:
            url = str(getattr(req, "full_url", ""))
            if "?t=" in url or "&t=" in url:
                return _mock_response(200, b"""
                    {"Response": "False", "Error": "Movie not found!"}
                """)
            return _mock_response(200, b"""
                {"Search": [], "totalResults": "0", "Response": "True"}
            """)

        with patch(PATCH_TARGET, side_effect=side_effect):
            result = omdb_search_poster("Unknown Movie", 2020, self.API_KEY)

        assert result is None

    def test_http_error(self) -> None:
        """Non-200 status code is handled gracefully."""
        with patch(PATCH_TARGET, return_value=_mock_response(401, b"{}")):
            result = omdb_search_poster("Any", 2000, self.API_KEY)

        assert result is None

    def test_network_error(self) -> None:
        """Network/connection error is handled gracefully."""
        with patch(PATCH_TARGET, side_effect=Exception("Connection refused")):
            result = omdb_search_poster("Any", 2000, self.API_KEY)

        assert result is None

    def test_invalid_json_response(self) -> None:
        """Malformed JSON response is handled gracefully."""
        with patch(PATCH_TARGET, return_value=_mock_response(200, b"not json")):
            result = omdb_search_poster("Any", 2000, self.API_KEY)

        assert result is None

    def test_year_param_in_url(self) -> None:
        """Year parameter is included in the URL when provided."""
        body = b'{"Title": "Test", "Poster": "http://poster.jpg", "Response": "True"}'
        with patch(PATCH_TARGET) as mock_urlopen:
            mock_urlopen.return_value = _mock_response(200, body)
            omdb_search_poster("Test", 2022, self.API_KEY)

        call_url = mock_urlopen.call_args[0][0].full_url
        assert "y=2022" in call_url
        assert "apikey=test_key_123" in call_url
        assert "t=Test" in call_url

    def test_search_parameter_in_url(self) -> None:
        """When exact fails, search uses ?s parameter."""
        call_log: list[str] = []

        def side_effect(req: Any, **kw: Any) -> MagicMock:
            url = str(getattr(req, "full_url", ""))
            call_log.append(url)
            if "?t=" in url or "&t=" in url:
                return _mock_response(200, b"""
                    {"Response": "False", "Error": "Movie not found!"}
                """)
            return _mock_response(200, b"""
                {"Search": [{"Title": "M", "Poster": "http://p.jpg",
                              "imdbID": "tt1"}], "Response": "True"}
            """)

        with patch(PATCH_TARGET, side_effect=side_effect):
            result = omdb_search_poster("My Movie", 2020, self.API_KEY)

        assert result is not None
        assert len(call_log) == 2
        assert "t=My+Movie" in call_log[0]
        assert "s=My+Movie" in call_log[1]
