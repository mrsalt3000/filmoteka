"""Unit tests for the ffprobe wrapper (mocked subprocess)."""

from __future__ import annotations

from pathlib import Path
from subprocess import TimeoutExpired
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from filmoteka.infrastructure.media_probe import (
    MediaProbeError,
    MediaProbeResult,
    _parse_probe_data,
    probe_media,
)

# ---------------------------------------------------------------------------
# _parse_probe_data
# ---------------------------------------------------------------------------


def test_parse_full_video() -> None:
    data: dict[str, Any] = {
        "format": {"duration": "123.456"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
            },
            {
                "index": 2,
                "codec_type": "audio",
                "codec_name": "mp3",
            },
            {
                "index": 3,
                "codec_type": "subtitle",
                "codec_name": "subrip",
            },
        ],
    }
    result = _parse_probe_data(data)
    assert result.duration_secs == 123.456
    assert result.width == 1920
    assert result.height == 1080
    assert result.codec == "h264"
    assert result.audio_codec == "aac"
    assert result.audio_count == 2
    assert result.subtitle_count == 1


def test_parse_no_streams() -> None:
    data = {"format": {"duration": "10.0"}, "streams": []}
    result = _parse_probe_data(data)
    assert result.duration_secs == 10.0
    assert result.width is None
    assert result.height is None
    assert result.codec is None
    assert result.audio_codec is None
    assert result.audio_count == 0
    assert result.subtitle_count == 0


def test_parse_no_format() -> None:
    data: dict[str, object] = {}
    result = _parse_probe_data(data)
    assert result.duration_secs is None
    assert result.width is None


def test_parse_duration_from_video_stream_when_format_missing() -> None:
    data = {
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "hevc",
                "width": 3840,
                "height": 2160,
                "duration": "99.999",
            }
        ]
    }
    result = _parse_probe_data(data)
    assert result.width == 3840
    assert result.height == 2160
    assert result.codec == "hevc"
    assert result.duration_secs == 99.999


def test_parse_audio_only() -> None:
    data = {
        "format": {"duration": "300.0"},
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "flac",
            }
        ],
    }
    result = _parse_probe_data(data)
    assert result.duration_secs == 300.0
    assert result.width is None
    assert result.height is None
    assert result.codec is None
    assert result.audio_codec == "flac"
    assert result.audio_count == 1
    assert result.subtitle_count == 0


# ---------------------------------------------------------------------------
# MediaProbeResult — frozen dataclass
# ---------------------------------------------------------------------------


def test_media_probe_result_immutable() -> None:
    result = MediaProbeResult(
        duration_secs=10.0,
        width=1920,
        height=1080,
        codec="h264",
        audio_codec="aac",
        audio_count=1,
        subtitle_count=0,
    )
    with pytest.raises(AttributeError):
        result.duration_secs = 20.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# probe_media — error cases
# ---------------------------------------------------------------------------


def test_probe_nonexistent_file() -> None:
    with pytest.raises(MediaProbeError, match="File does not exist"):
        probe_media(Path("/nonexistent/file.mkv"))


@patch("filmoteka.infrastructure.media_probe.subprocess.run")
def test_probe_ffprobe_not_found(mock_run: object) -> None:
    """When ffprobe is not on PATH, subprocess raises FileNotFoundError."""
    tmp = Path("/tmp/fake.mkv")
    with (
        patch.object(Path, "is_file", return_value=True),
        patch(
            "filmoteka.infrastructure.media_probe.subprocess.run",
            side_effect=FileNotFoundError,
        ),
        pytest.raises(MediaProbeError, match="ffprobe not found"),
    ):
        probe_media(tmp)


@patch("filmoteka.infrastructure.media_probe.subprocess.run")
def test_probe_ffprobe_timeout(mock_run: object) -> None:
    tmp = Path("/tmp/fake.mkv")
    with (
        patch.object(Path, "is_file", return_value=True),
        patch(
            "filmoteka.infrastructure.media_probe.subprocess.run",
            side_effect=TimeoutExpired("ffprobe", 60),
        ),
        pytest.raises(MediaProbeError, match="ffprobe timed out"),
    ):
        probe_media(tmp)


def test_probe_ffprobe_nonzero_exit() -> None:
    tmp = Path("/tmp/fake.mkv")
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "Invalid data found"
    with (
        patch.object(Path, "is_file", return_value=True),
        patch(
            "filmoteka.infrastructure.media_probe.subprocess.run",
            return_value=mock_result,
        ),
        pytest.raises(MediaProbeError, match="ffprobe failed"),
    ):
        probe_media(tmp)


def test_probe_invalid_json() -> None:
    tmp = Path("/tmp/fake.mkv")
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "not json at all"
    with (
        patch.object(Path, "is_file", return_value=True),
        patch(
            "filmoteka.infrastructure.media_probe.subprocess.run",
            return_value=mock_result,
        ),
        pytest.raises(MediaProbeError, match="invalid JSON"),
    ):
        probe_media(tmp)
