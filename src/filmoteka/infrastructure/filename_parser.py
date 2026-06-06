"""Filename parser — extract title, year, and quality from video file names."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Quality markers in order of preference (most specific / useful first).
# Resolution markers (\d+p, \d+K) come first so they are returned as
# the primary quality indicator over release-group markers (WEB-DL etc).
_QUALITY_MARKERS: list[re.Pattern[str]] = [
    re.compile(r"\d+[\s._-]*p"),  # 1080p, 2160p, 720p, 480p
    re.compile(r"\d+[\s._-]*K"),  # 4K
    re.compile(r"WEB[\s._-]*DL", re.IGNORECASE),
    re.compile(r"WEB[\s._-]*Rip", re.IGNORECASE),
    re.compile(r"Blue[\s._-]*Ray", re.IGNORECASE),
    re.compile(r"BLU[\s._-]*Ray", re.IGNORECASE),
    re.compile(r"BD[\s._-]*Rip", re.IGNORECASE),
    re.compile(r"HD[\s._-]*Rip", re.IGNORECASE),
    re.compile(r"DVD[\s._-]*Rip", re.IGNORECASE),
    re.compile(r"TV[\s._-]*Rip", re.IGNORECASE),
    re.compile(r"Tele[\s._-]*Sync", re.IGNORECASE),
    re.compile(r"Cam[\s._-]*Rip", re.IGNORECASE),
]

# Separator characters to replace with space in the title.
_SEPARATORS_RE = re.compile(r"[\s._\-]+")


@dataclass(frozen=True)
class ParsedFilename:
    """Result of parsing a video filename."""

    title: str
    year: int | None
    quality: str | None


def parse_filename(path: Path) -> ParsedFilename:
    """Parse *path*'s stem and extract title, year, and quality.

    Returns ``ParsedFilename`` even when nothing can be extracted — in that
    case the whole stem is used as the title and the other fields are ``None``.
    """
    stem = path.stem  # filename without extension

    # 1. Extract and remove all quality markers so they don't pollute the
    #    title and don't shift year positions.  ``quality`` keeps the first
    #    (most specific) match.
    quality: str | None = None
    for pattern in _QUALITY_MARKERS:
        match = pattern.search(stem)
        if match:
            if quality is None:
                quality = _normalise_quality(match.group(0))
            stem = stem[:match.start()] + stem[match.end():]

    # 2. Extract year from the cleaned stem.
    year: int | None = None
    year_match = re.search(r"(19\d\d|20[0-2]\d)", stem)
    if year_match:
        year = int(year_match.group(1))

    # 3. Build title: remove year, clean separators, strip.
    if year_match:
        title_before = stem[:year_match.start()]
        title_after = stem[year_match.end():]
        title_raw = title_before + title_after
    else:
        title_raw = stem

    title = _clean_title(title_raw)

    return ParsedFilename(title=title, year=year, quality=quality)


def _normalise_quality(raw: str) -> str:
    """Normalise a quality token to a canonical form."""
    # Remove spaces/separators around 'p' — "1080 p" → "1080p"
    normalised = re.sub(r"\s+", "", raw)
    return normalised.upper() if normalised.isupper() else normalised


def _clean_title(raw: str) -> str:
    """Replace separators with spaces, strip leading/trailing cruft."""
    title = _SEPARATORS_RE.sub(" ", raw).strip()
    # Remove leading/trailing non-alphanumeric characters except spaces.
    title = re.sub(r"^[^a-zA-Zа-яёА-ЯЁ0-9]+", "", title)
    title = re.sub(r"[^a-zA-Zа-яёА-ЯЁ0-9]+$", "", title)
    return title.strip()
