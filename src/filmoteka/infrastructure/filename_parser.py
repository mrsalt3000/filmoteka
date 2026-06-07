"""Filename parser — extract title, year, quality, language, and edition from video file names."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Quality markers in order of preference (most specific / useful first).
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
    re.compile(r"HDR\d*", re.IGNORECASE),  # HDR, HDR10, HDR10+
    re.compile(r"Dolby[\s._-]*Vision", re.IGNORECASE),
    re.compile(r"10[\s._-]*bit", re.IGNORECASE),
]

# Language markers — removed from stem during parsing.
_LANGUAGE_MARKERS: list[re.Pattern[str]] = [
    re.compile(r"(?<![a-zA-Z])RUS(?![a-zA-Z])"),
    re.compile(r"(?<![a-zA-Z])DUB(?:bed)?(?![a-zA-Z])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Z])SUB(?:titles?)?(?![a-zA-Z])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Z])Original(?![a-zA-Z])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Z])ENG(?:lish)?(?![a-zA-Z])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Z])Multi(?![a-zA-Z])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Z])JPN(?:anese)?(?![a-zA-Z])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Z])FR(?:ench)?(?![a-zA-Z])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Z])GER(?:man)?(?![a-zA-Z])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Z])ITA(?:lian)?(?![a-zA-Z])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Z])SPA(?:nish)?(?![a-zA-Z])", re.IGNORECASE),
]

# Edition markers — removed from stem during parsing.
_EDITION_MARKERS: list[re.Pattern[str]] = [
    re.compile(r"Director'?s?[\s._-]*Cut", re.IGNORECASE),
    re.compile(r"Extended[\s._-]*Cut", re.IGNORECASE),
    re.compile(r"Theatrical[\s._-]*Cut", re.IGNORECASE),
    re.compile(r"Theatrical", re.IGNORECASE),
    re.compile(r"Uncut", re.IGNORECASE),
    re.compile(r"Unrated", re.IGNORECASE),
    re.compile(r"Remaster(?:ed)?", re.IGNORECASE),
    re.compile(r"Criterion", re.IGNORECASE),
    re.compile(r"IMAX", re.IGNORECASE),
    re.compile(r"3D[\s._-]*SBS", re.IGNORECASE),
    re.compile(r"Open[\s._-]*Matte", re.IGNORECASE),
]

_SEPARATORS_RE = re.compile(r"[\s._\-]+")


@dataclass(frozen=True)
class ParsedFilename:
    """Result of parsing a video filename."""

    title: str
    year: int | None
    quality: str | None
    language: str | None = None
    edition_type: str | None = None


def _extract_markers(
    stem: str,
    patterns: list[re.Pattern[str]],
) -> tuple[str, str | None]:
    """Remove all matching markers from *stem* and return the first match.

    Returns ``(cleaned_stem, first_match)``.  Matches are removed so they
    do not pollute the title.
    """
    first: str | None = None
    for pattern in patterns:
        match = pattern.search(stem)
        while match:
            if first is None:
                first = match.group(0)
            stem = stem[:match.start()] + stem[match.end():]
            match = pattern.search(stem)
    return stem, first


def parse_filename(path: Path) -> ParsedFilename:
    """Parse *path*'s stem and extract title, year, quality, language, and edition.

    Returns ``ParsedFilename`` even when nothing can be extracted — in that
    case the whole stem is used as the title and the other fields are ``None``.
    """
    stem = path.stem

    # 1. Extract and remove quality markers.
    quality: str | None = None
    for pattern in _QUALITY_MARKERS:
        match = pattern.search(stem)
        if match:
            if quality is None:
                quality = _normalise_quality(match.group(0))
            stem = stem[:match.start()] + stem[match.end():]

    # 2. Extract and remove edition markers.
    stem, edition_type = _extract_markers(stem, _EDITION_MARKERS)

    # 3. Extract and remove language markers.
    stem, language = _extract_markers(stem, _LANGUAGE_MARKERS)

    # 4. Extract year from the cleaned stem.
    year: int | None = None
    year_match = re.search(r"(19\d\d|20[0-2]\d)", stem)
    if year_match:
        year = int(year_match.group(1))

    # 5. Build title: remove year, clean separators, strip.
    if year_match:
        title_before = stem[:year_match.start()]
        title_after = stem[year_match.end():]
        title_raw = title_before + title_after
    else:
        title_raw = stem

    title = _clean_title(title_raw)

    return ParsedFilename(
        title=title,
        year=year,
        quality=quality,
        language=language,
        edition_type=edition_type,
    )


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
