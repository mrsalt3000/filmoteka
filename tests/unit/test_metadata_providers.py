"""Unit tests for external metadata providers — OMDB poster search."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from filmoteka.infrastructure.metadata_providers import omdb_search_poster

PATCH_TARGET = "filmoteka.infrastructure.metadata_providers.urlopen"


def _mock_response(status: int, body: bytes) -> MagicMock:
    m = MagicMock()
    m.status = status
    m.read.return_value = body
    return m


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
