"""ffprobe wrapper for media file analysis."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class MediaProbeError(Exception):
    """Raised when media probing fails."""


@dataclass(frozen=True)
class MediaProbeResult:
    """Result of probing a media file with ffprobe."""

    duration_secs: float | None
    width: int | None
    height: int | None
    codec: str | None
    audio_codec: str | None
    audio_count: int
    subtitle_count: int


def probe_media(path: Path) -> MediaProbeResult:
    """Probe *path* with ffprobe and return structured metadata.

    Raises ``MediaProbeError`` if the file does not exist, is not a valid
    media file, or ffprobe is not available.
    """
    if not path.is_file():
        raise MediaProbeError(f"File does not exist: {path}")

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        raise MediaProbeError("ffprobe not found — is ffmpeg installed?") from None
    except subprocess.TimeoutExpired:
        raise MediaProbeError(f"ffprobe timed out on: {path}") from None

    if result.returncode != 0:
        raise MediaProbeError(
            f"ffprobe failed on {path}: {result.stderr.strip()}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaProbeError(
            f"ffprobe returned invalid JSON for {path}: {exc}"
        ) from None

    return _parse_probe_data(data)


def _parse_probe_data(data: dict[str, Any]) -> MediaProbeResult:
    """Parse the ffprobe JSON output into a ``MediaProbeResult``."""
    fmt: dict[str, Any] = data.get("format") or {}
    streams: list[dict[str, Any]] = data.get("streams") or []

    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]

    duration_raw = fmt.get("duration")
    duration_secs = float(duration_raw) if duration_raw else None

    # Fallback: get duration from the first video stream if format lacks it
    if duration_secs is None and video_streams:
        d = video_streams[0].get("duration")
        if d is not None:
            duration_secs = float(d)

    width: int | None = None
    height: int | None = None
    codec: str | None = None

    if video_streams:
        vs = video_streams[0]
        width = vs.get("width")
        height = vs.get("height")
        codec = vs.get("codec_name")

    audio_codec: str | None = None
    if audio_streams:
        audio_codec = audio_streams[0].get("codec_name")

    audio_count = len(audio_streams)
    subtitle_count = len(subtitle_streams)

    return MediaProbeResult(
        duration_secs=duration_secs,
        width=width,
        height=height,
        codec=codec,
        audio_codec=audio_codec,
        audio_count=audio_count,
        subtitle_count=subtitle_count,
    )
