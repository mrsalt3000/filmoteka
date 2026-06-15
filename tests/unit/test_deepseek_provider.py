"""Unit tests for DeepSeek provider — search info extraction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from filmoteka.infrastructure.deepseek_provider import deepseek_extract_search_info

PATCH_TARGET = "filmoteka.infrastructure.deepseek_provider.urlopen"
API_KEY = "test_ds_key_456"


def _mock_response(status: int, body: bytes) -> MagicMock:
    m = MagicMock()
    m.status = status
    m.read.return_value = body
    return m


def _build_deepseek_body(
    content: str,
    finish_reason: str = "stop",
) -> bytes:
    """Build a DeepSeek /v1/chat/completions response body."""
    body = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "deepseek-chat",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 50, "completion_tokens": 30, "total_tokens": 80},
    }
    import json
    return json.dumps(body).encode("utf-8")


# ---------------------------------------------------------------------------
# deepseek_extract_search_info — happy path
# ---------------------------------------------------------------------------


class TestDeepseekExtractSearchInfo:
    """deepseek_extract_search_info — structured title + year + type."""

    def test_movie_extraction(self) -> None:
        """DeepSeek returns movie info → parsed correctly."""
        body = _build_deepseek_body(
            '{"title": "The Matrix", "year": 1999, "type": "movie"}',
        )
        with patch(PATCH_TARGET, return_value=_mock_response(200, body)):
            result = deepseek_extract_search_info(
                "The.Matrix.1999.1080p.BluRay.x264", API_KEY,
            )

        assert result is not None
        assert result["title"] == "The Matrix"
        assert result["year"] == 1999
        assert result["type"] == "movie"

    def test_series_extraction(self) -> None:
        """DeepSeek returns series info → parsed correctly."""
        body = _build_deepseek_body(
            '{"title": "Gravity Falls", "year": 2012, "type": "series"}',
        )
        with patch(PATCH_TARGET, return_value=_mock_response(200, body)):
            result = deepseek_extract_search_info(
                "Gravity.Falls.S01E01.IVI.SOFCI", API_KEY,
            )

        assert result is not None
        assert result["title"] == "Gravity Falls"
        assert result["year"] == 2012
        assert result["type"] == "series"

    def test_series_extraction_from_filename(self) -> None:
        """Series detected from SxxExx filename pattern."""
        body = _build_deepseek_body(
            '{"title": "The Mandalorian", "year": 2020, "type": "series"}',
        )
        with patch(PATCH_TARGET, return_value=_mock_response(200, body)):
            result = deepseek_extract_search_info(
                "The.Mandalorian.S02E03.Chapter.11.2160p", API_KEY,
            )

        assert result is not None
        assert result["title"] == "The Mandalorian"
        assert result["year"] == 2020
        assert result["type"] == "series"

    def test_markdown_wrapped_json(self) -> None:
        """DeepSeek returns markdown-wrapped JSON → parsed correctly."""
        body = _build_deepseek_body(
            "```json\n{\"title\": \"Inception\", \"year\": 2010, \"type\": \"movie\"}\n```",
        )
        with patch(PATCH_TARGET, return_value=_mock_response(200, body)):
            result = deepseek_extract_search_info("Inception.2010.1080p", API_KEY)

        assert result is not None
        assert result["title"] == "Inception"
        assert result["year"] == 2010
        assert result["type"] == "movie"

    def test_year_as_string(self) -> None:
        """DeepSeek returns year as string → coerce to int."""
        body = _build_deepseek_body(
            '{"title": "Test", "year": "2021", "type": "movie"}',
        )
        with patch(PATCH_TARGET, return_value=_mock_response(200, body)):
            result = deepseek_extract_search_info("Test.2021.1080p", API_KEY)

        assert result is not None
        assert result["year"] == 2021

    def test_null_type(self) -> None:
        """DeepSeek returns null type → result type is None."""
        body = _build_deepseek_body(
            '{"title": "Some Video", "year": null, "type": null}',
        )
        with patch(PATCH_TARGET, return_value=_mock_response(200, body)):
            result = deepseek_extract_search_info(
                "Some.Video.2020.1080p", API_KEY,
            )

        assert result is not None
        assert result["title"] == "Some Video"
        assert result["year"] is None
        assert result["type"] is None

    def test_type_normalised(self) -> None:
        """Type 'MOVIE' and 'Series' are normalised to lowercase."""
        body = _build_deepseek_body(
            '{"title": "Test", "year": 2020, "type": "MOVIE"}',
        )
        with patch(PATCH_TARGET, return_value=_mock_response(200, body)):
            result = deepseek_extract_search_info("Test.2020", API_KEY)

        assert result is not None
        assert result["type"] == "movie"


# ---------------------------------------------------------------------------
# deepseek_extract_search_info — error recovery / fallback
# ---------------------------------------------------------------------------


class TestDeepseekExtractSearchInfoFallback:
    """Fallback to clean_title_for_omdb when DeepSeek is unavailable."""

    def test_non_200_status(self) -> None:
        """Non-200 response → fallback to clean_title_for_omdb."""
        with patch(PATCH_TARGET, return_value=_mock_response(401, b"{}")):
            result = deepseek_extract_search_info(
                "The.Matrix.1999.1080p.BluRay.x264", API_KEY,
            )

        assert result is not None
        # Fallback uses clean_title_for_omdb
        assert "The Matrix" in result["title"]
        assert result["year"] == 1999
        assert result["type"] is None  # heuristic fallback has no type

    def test_network_error(self) -> None:
        """Network error → fallback to clean_title_for_omdb."""
        with patch(PATCH_TARGET, side_effect=Exception("Connection refused")):
            result = deepseek_extract_search_info(
                "Inception.2010.1080p", API_KEY,
            )

        assert result is not None
        assert "Inception" in result["title"]
        assert result["year"] == 2010
        assert result["type"] is None

    def test_invalid_json_response(self) -> None:
        """Invalid JSON response → fallback."""
        body = _build_deepseek_body("not json at all")
        with patch(PATCH_TARGET, return_value=_mock_response(200, body)):
            result = deepseek_extract_search_info(
                "Test.Movie.2020.HDRip", API_KEY,
            )

        assert result is not None
        assert result["type"] is None  # fallback

    def test_empty_content(self) -> None:
        """Empty assistant content → fallback."""
        body = _build_deepseek_body("")
        with patch(PATCH_TARGET, return_value=_mock_response(200, body)):
            result = deepseek_extract_search_info(
                "Test.Movie.2020", API_KEY,
            )

        assert result is not None
        assert result["type"] is None

    def test_missing_title(self) -> None:
        """JSON without 'title' field → fallback."""
        body = _build_deepseek_body('{"year": 2020, "type": "movie"}')
        with patch(PATCH_TARGET, return_value=_mock_response(200, body)):
            result = deepseek_extract_search_info(
                "Test.Movie.2020", API_KEY,
            )

        assert result is not None
        assert result["type"] is None  # fallback

    def test_fallback_cleans_markers(self) -> None:
        """Fallback strips tech markers from the raw stem."""
        with patch(PATCH_TARGET, return_value=_mock_response(401, b"{}")):
            result = deepseek_extract_search_info(
                "Брат.1997.WEB-DLRip-AVC_[New-team]_by_AVP_Studio", API_KEY,
            )

        assert result is not None
        assert result["title"] == "Брат"
        assert result["year"] == 1997
        assert result["type"] is None
