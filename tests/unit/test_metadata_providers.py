"""Unit tests for external metadata providers — TMDb poster search."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from filmoteka.infrastructure.metadata_providers import tmdb_search_poster


def _mock_response(status: int, body: bytes) -> MagicMock:
    m = MagicMock()
    m.status = status
    m.read.return_value = body
    return m


class TestTmdbSearchPoster:
    """tmdb_search_poster — poster URL lookup via TMDb API."""

    API_KEY = "test_key_123"

    def test_found_with_year(self) -> None:
        """Happy path — movie found with poster, year matches."""
        body = b"""
        {
            "results": [
                {"poster_path": "/abc123.jpg", "title": "The Matrix", "release_date": "1999-03-31"}
            ]
        }
        """
        with patch("filmoteka.infrastructure.metadata_providers.urlopen", return_value=_mock_response(200, body)):
            result = tmdb_search_poster("The Matrix", 1999, self.API_KEY)

        assert result is not None
        url, source = result
        assert url == "https://image.tmdb.org/t/p/w500/abc123.jpg"
        assert source == "tmdb"

    def test_found_without_year(self) -> None:
        """Poster found when year is None."""
        body = b"""
        {
            "results": [
                {"poster_path": "/xyz789.jpg", "title": "Some Movie"}
            ]
        }
        """
        with patch("filmoteka.infrastructure.metadata_providers.urlopen", return_value=_mock_response(200, body)):
            result = tmdb_search_poster("Some Movie", None, self.API_KEY)

        assert result is not None
        url, source = result
        assert url == "https://image.tmdb.org/t/p/w500/xyz789.jpg"

    def test_no_results(self) -> None:
        """Empty results list — no poster found."""
        body = b'{"results": []}'
        with patch("filmoteka.infrastructure.metadata_providers.urlopen", return_value=_mock_response(200, body)):
            result = tmdb_search_poster("Unknown Movie", 2020, self.API_KEY)

        assert result is None

    def test_no_poster_path(self) -> None:
        """Result exists but has no poster_path."""
        body = b"""
        {
            "results": [
                {"poster_path": null, "title": "No Poster Film"}
            ]
        }
        """
        with patch("filmoteka.infrastructure.metadata_providers.urlopen", return_value=_mock_response(200, body)):
            result = tmdb_search_poster("No Poster Film", None, self.API_KEY)

        assert result is None

    def test_http_error(self) -> None:
        """Non-200 status code is handled gracefully."""
        with patch("filmoteka.infrastructure.metadata_providers.urlopen", return_value=_mock_response(401, b"{}")):
            result = tmdb_search_poster("Any", 2000, self.API_KEY)

        assert result is None

    def test_network_error(self) -> None:
        """Network/connection error is handled gracefully."""
        with patch(
            "filmoteka.infrastructure.metadata_providers.urlopen",
            side_effect=Exception("Connection refused"),
        ):
            result = tmdb_search_poster("Any", 2000, self.API_KEY)

        assert result is None

    def test_invalid_json_response(self) -> None:
        """Malformed JSON response is handled gracefully."""
        with patch("filmoteka.infrastructure.metadata_providers.urlopen", return_value=_mock_response(200, b"not json")):
            result = tmdb_search_poster("Any", 2000, self.API_KEY)

        assert result is None

    def test_year_param_in_url(self) -> None:
        """Year parameter is included in the URL when provided."""
        body = b'{"results": [{"poster_path": "/test.jpg"}]}'
        with patch("filmoteka.infrastructure.metadata_providers.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _mock_response(200, body)
            tmdb_search_poster("Test", 2022, self.API_KEY)

        # Verify year was in the URL
        call_url = mock_urlopen.call_args[0][0].full_url
        assert "year=2022" in call_url
        assert "api_key=test_key_123" in call_url
        assert "query=Test" in call_url
