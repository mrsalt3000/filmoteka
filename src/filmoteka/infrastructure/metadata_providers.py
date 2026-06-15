"""External metadata provider layer — OMDB poster search.

V1 scope: poster search via OMDB API (www.omdbapi.com).
External data is unreliable; always store source and confidence
for later review (V1-005).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import cast
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

OMDB_API_BASE = "http://www.omdbapi.com"


# ---------------------------------------------------------------------------
# Title normalisation for OMDB queries
# ---------------------------------------------------------------------------


@dataclass
class CleanedTitle:
    """Result of cleaning a raw title for OMDB search."""

    title: str
    year: int | None


# Tech markers to strip from titles before sending to OMDB.
_TECH_MARKERS: list[re.Pattern[str]] = [
    # Release types
    re.compile(r"WEB[\s._-]*DL(?:Rip)?", re.IGNORECASE),
    re.compile(r"WEB[\s._-]*Rip", re.IGNORECASE),
    re.compile(r"HDTV(?:Rip)?", re.IGNORECASE),
    re.compile(r"\bHDRip\b", re.IGNORECASE),
    re.compile(r"Blu[\s._-]*Ray", re.IGNORECASE),
    re.compile(r"BDRip", re.IGNORECASE),
    re.compile(r"DVD(?:Rip|[5-9])", re.IGNORECASE),
    re.compile(r"SAT[\s._-]*Rip", re.IGNORECASE),
    re.compile(r"TV[\s._-]*Rip", re.IGNORECASE),
    re.compile(r"Tele[\s._-]*Sync", re.IGNORECASE),
    re.compile(r"Cam[\s._-]*Rip", re.IGNORECASE),
    re.compile(r"Pay[\s._-]*Per[\s._-]*View", re.IGNORECASE),
    re.compile(r"PPV", re.IGNORECASE),
    # Resolutions
    re.compile(r"\d+[\s._-]*[pK](?:60)?", re.IGNORECASE),  # 1080p, 2160p, 4K, 720p60
    re.compile(r"Ultra[\s._-]*HD", re.IGNORECASE),
    re.compile(r"UHD", re.IGNORECASE),
    re.compile(r"Full[\s._-]*HD", re.IGNORECASE),
    re.compile(r"FHD", re.IGNORECASE),
    # HDR / colour
    re.compile(r"HDR\d*", re.IGNORECASE),
    re.compile(r"Dolby[\s._-]*Vision", re.IGNORECASE),
    re.compile(r"10[\s._-]*bit", re.IGNORECASE),
    re.compile(r"8[\s._-]*bit", re.IGNORECASE),
    re.compile(r"SDR", re.IGNORECASE),
    re.compile(r"BT[.\s]*2020", re.IGNORECASE),
    re.compile(r"BT[.\s]*709", re.IGNORECASE),
    # Video codecs
    re.compile(r"[HX][.\s]*26[45]", re.IGNORECASE),
    re.compile(r"\bAVC\b", re.IGNORECASE),
    re.compile(r"\bHEVC\b", re.IGNORECASE),
    re.compile(r"\bVP[89]\b", re.IGNORECASE),
    re.compile(r"\bAV1\b", re.IGNORECASE),
    re.compile(r"\bMPEG[\s._-]*2\b", re.IGNORECASE),
    re.compile(r"\bDivX\b", re.IGNORECASE),
    re.compile(r"\bXvid\b", re.IGNORECASE),
    # Audio codecs / formats
    re.compile(r"\bAC3\b", re.IGNORECASE),
    re.compile(r"\bAAC(?:LC)?\b", re.IGNORECASE),
    re.compile(r"\bDTS(?:[\s._-]*HD)?\b", re.IGNORECASE),
    re.compile(r"\bTrueHD\b", re.IGNORECASE),
    re.compile(r"\bE[\s._-]*AC3\b", re.IGNORECASE),
    re.compile(r"\bFLAC\b", re.IGNORECASE),
    re.compile(r"\bMP3\b", re.IGNORECASE),
    re.compile(r"\bPCM\b", re.IGNORECASE),
    re.compile(r"Dolby[\s._-]*Digital", re.IGNORECASE),
    # Languages
    re.compile(r"(?<![a-zA-Zа-яё])RUS(?:SIAN)?(?![a-zA-Zа-яё])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Zа-яё])DUB(?:bed|lyazh)?(?![a-zA-Zа-яё])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Zа-яё])SUB(?:titles?|bed)?(?![a-zA-Zа-яё])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Zа-яё])Original(?![a-zA-Zа-яё])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Zа-яё])ENG(?:lish)?(?![a-zA-Zа-яё])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Zа-яё])PУС\b", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Zа-яё])Multi(?![a-zA-Zа-яё])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Zа-яё])JPN(?:anese)?(?![a-zA-Zа-яё])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Zа-яё])FR(?:ench)?(?![a-zA-Zа-яё])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Zа-яё])GER(?:man)?(?![a-zA-Zа-яё])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Zа-яё])ITA(?:lian)?(?![a-zA-Zа-яё])", re.IGNORECASE),
    re.compile(r"(?<![a-zA-Zа-яё])SPA(?:nish)?(?![a-zA-Zа-яё])", re.IGNORECASE),
    # Edition markers
    re.compile(r"Director'?s?[\s._-]*Cut", re.IGNORECASE),
    re.compile(r"Extended[\s._-]*Cut", re.IGNORECASE),
    re.compile(r"Theatrical[\s._-]*Cut", re.IGNORECASE),
    re.compile(r"Remaster(?:ed)?", re.IGNORECASE),
    re.compile(r"Criterion", re.IGNORECASE),
    re.compile(r"IMAX", re.IGNORECASE),
    re.compile(r"Open[\s._-]*Matte", re.IGNORECASE),
]

# Tournament / broadcast tails.
_BROADCAST_TAILS: list[re.Pattern[str]] = [
    re.compile(r"Main[\s._-]*Card", re.IGNORECASE),
    re.compile(r"\bPrelims?\b", re.IGNORECASE),
    re.compile(r"Predvaritelnyj[\s._-]*Kard", re.IGNORECASE),
    re.compile(r"Preliminary[\s._-]*Card", re.IGNORECASE),
    re.compile(r"Early[\s._-]*Prelims?", re.IGNORECASE),
    re.compile(r"UFC[\s._-]*\d+", re.IGNORECASE),
    re.compile(r"Bellator[\s._-]*\d+", re.IGNORECASE),
    re.compile(r"PFL[\s._-]*\d+", re.IGNORECASE),
    re.compile(r"\b(Season|Episode|Series)\b", re.IGNORECASE),
]

# Patterns for bracketed groups: [New_team], (AVP), {group}
# NOTE: do NOT match `(1994)` — those are years, not group tags.
_BRACKETED_GROUPS = re.compile(r"[\[{][^\]}]*[\}\]}]")

# Scene group markers: "by_GroupName" or "by Group Name" after cleanup.
_SCENE_GROUP = re.compile(r"\bby[\s._-]+[A-Za-z][A-Za-z0-9_.\s-]*\b")


def _remove_patterns(text: str, patterns: list[re.Pattern[str]]) -> str:
    """Remove all occurrences of *patterns* from *text*."""
    for pat in patterns:
        text = pat.sub(" ", text)
    return text


def clean_title_for_omdb(raw: str) -> CleanedTitle:
    """Clean a raw title for OMDB search queries.

    Strips tech markers (HDTVRip, 1080p, WEB-DL, x264, RUS, DUB, etc.),
    broadcast tails (Main Card, Prelims), bracketed group tags, normalises
    separators, and extracts the year.

    Returns ``CleanedTitle`` with a clean title string and optionally the
    extracted year.
    """
    text = raw

    # 1. Remove bracketed groups first (most aggressive)
    text = _BRACKETED_GROUPS.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # 2. Replace separators with spaces for uniform matching
    text = re.sub(r"[\s._\-]+", " ", text)

    # 3. Remove tech markers
    text = _remove_patterns(text, _TECH_MARKERS)
    text = re.sub(r"\s+", " ", text).strip()

    # 4. Remove scene group markers (by_GroupName)
    text = _SCENE_GROUP.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # 5. Remove broadcast tails
    text = _remove_patterns(text, _BROADCAST_TAILS)
    text = re.sub(r"\s+", " ", text).strip()

    # 6. Extract year — look for (1999) or 1999 surrounded by spaces/end
    year: int | None = None
    year_match = re.search(r"\((\d{4})\)", text)
    if year_match:
        year = int(year_match.group(1))
        text = text[:year_match.start()] + " " + text[year_match.end():]
    else:
        year_match = re.search(r"(?:^|\s)((?:19\d\d|20[0-2]\d))(?:\s|$)", text)
        if year_match:
            year = int(year_match.group(1))
            text = text[:year_match.start()] + " " + text[year_match.end():]

    # 7. Normalise dashes, colons, multiple spaces
    text = re.sub(r"[–—−]", "-", text)
    text = re.sub(r"\s*:\s*", ": ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s*-\s*", " - ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # 8. Strip leading/trailing non-alphanumeric
    text = re.sub(r"^[^a-zA-Zа-яёА-ЯЁ0-9]+", "", text)
    text = re.sub(r"[^a-zA-Zа-яёА-ЯЁ0-9)]+$", "", text)

    return CleanedTitle(title=text.strip(), year=year)


def detect_search_type(
    film_title: str,
    series_id: int | None = None,
) -> str | None:
    """Heuristically determine OMDB search type (movie / series / episode).

    Returns ``"series"``, ``"movie"``, or ``None`` when uncertain.
    """
    if series_id is not None:
        return "series"

    title_lower = film_title.lower()
    # Keywords that strongly suggest a series/show
    series_kw = r"\b(season|episode|series|mini[\s._-]*series|tv[\s._-]*series|s\d{1,2}e\d{1,2})\b"
    if re.search(series_kw, title_lower, re.IGNORECASE):
        return "series"

    return "movie"


# ---------------------------------------------------------------------------
# Poster search — v2 (type-aware, multi-step)
# ---------------------------------------------------------------------------


def omdb_search_poster_v2(
    cleaned: CleanedTitle,
    api_key: str,
    type_: str | None = None,
) -> tuple[str, str] | None:
    """Search OMDB for a poster using a type-aware multi-step strategy.

    Steps:
    1. Exact title match with type: ``?t=<title>&y=<year>&type=<type>``
    2. Fuzzy search with type: ``?s=<title>&y=<year>&type=<type>``
    3. IMDb ID lookup from best candidate: ``?i=<imdbID>``
    4. If ``type_`` is ``None``, repeat 1–3 with ``type=series`` then ``type=movie``
    5. Fallback: ``?s=<title>`` without year or type

    Returns ``(poster_url, "omdb")`` on success, or ``None``.
    """
    title = cleaned.title
    year = cleaned.year

    types_to_try: list[str | None] = [type_] if type_ else [None, "series", "movie"]

    for try_type in types_to_try:
        result = _omdb_v2_exact(title, year, api_key, try_type)
        if result is not None:
            return result

        result = _omdb_v2_search_fallback(title, year, api_key, try_type)
        if result is not None:
            return result

        # If we already tried with a concrete type and found nothing on s=
        # (which also tries i= internally), stop doubling for None.
        if try_type is not None:
            continue

    # Final fallback — legacy s= without year/type
    logger.info("OMDB v2 final fallback for %r — s= without year/type", title)
    results = _omdb_search(title, None, api_key)
    if results is not None:
        for r in results:
            poster_url = _extract_poster(r)
            if poster_url is not None:
                logger.info(
                    "OMDB poster found for %r (final fallback, match %s): %s",
                    title, r.get("Title", "?"), poster_url,
                )
                return (poster_url, "omdb")

    logger.info("OMDB poster not found for %r (year=%s)", title, year)
    return None


def _omdb_v2_exact(
    title: str,
    year: int | None,
    api_key: str,
    type_: str | None,
) -> tuple[str, str] | None:
    """Step 1: exact ``?t=`` query with optional type."""
    result = _omdb_get(title, year, api_key, exact=True, type_=type_)
    if result is not None:
        poster_url = _extract_poster(result)
        if poster_url is not None:
            type_tag = f" type={type_}" if type_ else ""
            logger.info(
                "OMDB poster found for %r (exact%s): %s",
                title, type_tag, poster_url,
            )
            return (poster_url, "omdb")
    return None


def _omdb_v2_search_fallback(
    title: str,
    year: int | None,
    api_key: str,
    type_: str | None,
) -> tuple[str, str] | None:
    """Steps 2–3: ``?s=`` search + ``?i=`` IMDb ID lookup."""
    results = _omdb_get(title, year, api_key, exact=False, type_=type_)
    if results is None:
        return None

    raw_results: object = results.get("Search")
    if raw_results is None:
        return None

    candidates = cast(list[dict[str, object]], raw_results)
    if not candidates:
        return None

    # Step 2: find best candidate, check poster
    best = _pick_best_candidate(candidates, title, year)
    if best is not None:
        poster_url = _extract_poster(best)
        if poster_url is not None:
            type_tag = f" type={type_}" if type_ else ""
            logger.info(
                "OMDB poster found for %r (search%s, match %s): %s",
                title, type_tag, best.get("Title", "?"), poster_url,
            )
            return (poster_url, "omdb")

    # Step 3: IMDb ID lookup from best candidate
    if best is not None:
        imdb_id: object = best.get("imdbID")
        if imdb_id and isinstance(imdb_id, str) and imdb_id.startswith("tt"):
            imdb_result = _omdb_get_by_imdb_id(imdb_id, api_key)
            if imdb_result is not None:
                poster_url = _extract_poster(imdb_result)
                if poster_url is not None:
                    logger.info(
                        "OMDB poster found for %r (imdb=%s): %s",
                        title, imdb_id, poster_url,
                    )
                    return (poster_url, "omdb")

    return None


def _pick_best_candidate(
    candidates: list[dict[str, object]],
    title: str,
    year: int | None,
) -> dict[str, object] | None:
    """Pick the best matching candidate from ``?s=`` search results.

    Prefers candidates whose title is a case-insensitive substring match
    and whose year (if given) matches the request *year*.
    """
    if not candidates:
        return None

    # Score each candidate
    scored: list[tuple[int, dict[str, object]]] = []
    title_lower = title.lower()

    for c in candidates:
        c_title: object = c.get("Title", "")
        c_title_str = str(c_title) if c_title else ""
        score = 0

        # Substring match (strong signal)
        if c_title_str.lower() == title_lower:
            score += 3
        elif title_lower in c_title_str.lower() or c_title_str.lower() in title_lower:
            score += 2

        # Year match
        if year is not None:
            c_year_str = str(c.get("Year", "") or "")
            # OMDB Year may be "1999" or "1999–2000" (range for series)
            c_year = c_year_str[:4] if c_year_str else ""
            if c_year.isdigit() and int(c_year) == year:
                score += 1

        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][1]

    # Only return if at least a substring match
    if scored[0][0] >= 1:
        return best
    return None


# ---------------------------------------------------------------------------
# Poster search — legacy API
# ---------------------------------------------------------------------------


def omdb_search_poster(
    title: str,
    year: int | None,
    api_key: str,
) -> tuple[str, str] | None:
    """Search OMDB for a poster URL matching *title* and optional *year*.

    Returns ``(poster_url, source)`` on success, or ``None`` if no poster
    is found.  The source string is ``"omdb"``.

    Uses a two-level strategy:
    1. Exact title match via ``?t=title&y=year``.
    2. Fuzzy search via ``?s=title&y=year`` if exact match yields no poster.

    This is best-effort — network errors, missing results, or invalid API
    keys are logged and return ``None`` rather than raising.

    .. note::
       New code should prefer :func:`omdb_search_poster_v2` which supports
       ``type=`` filtering and ``i=`` (IMDb ID) fallback.
    """
    # Level 1 — exact title match
    result = _omdb_get(title, year, api_key, exact=True)
    if result is not None:
        poster_url = _extract_poster(result)
        if poster_url is not None:
            logger.info("OMDB poster found for %r (exact): %s", title, poster_url)
            return (poster_url, "omdb")

    # Level 2 — fuzzy search
    results = _omdb_search(title, year, api_key)
    if results is not None:
        for r in results:
            poster_url = _extract_poster(r)
            if poster_url is not None:
                movie_title = r.get("Title", "?")
                logger.info(
                    "OMDB poster found for %r (fuzzy match %r): %s",
                    title, movie_title, poster_url,
                )
                return (poster_url, "omdb")

    logger.info("OMDB poster not found for %r (year=%s)", title, year)
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _omdb_get(
    title: str,
    year: int | None,
    api_key: str,
    exact: bool = True,
    type_: str | None = None,
) -> dict[str, object] | None:
    """Query OMDB by title.

    If *exact* is ``True``, uses ``?t=`` parameter (single result).
    Otherwise uses ``?s=`` parameter (search, returns list).

    *type_* — optional OMDB ``type`` filter: ``"movie"``, ``"series"``,
    or ``"episode"``.  When ``None``, no type filter is sent.

    Returns the parsed JSON body on success, or ``None`` on error.
    """
    try:
        params: dict[str, str] = {"apikey": api_key}
        if exact:
            params["t"] = title
        else:
            params["s"] = title
        if year is not None:
            params["y"] = str(year)
        if type_ is not None:
            params["type"] = type_

        url = f"{OMDB_API_BASE}/?{urlencode(params)}"
        req = Request(url, headers={"Accept": "application/json"})
        resp = urlopen(req, timeout=10)

        if resp.status != 200:
            logger.warning("OMDB %s returned %s", title, resp.status)
            return None

        body: dict[str, object] = json.loads(resp.read().decode("utf-8"))

        # OMDB returns {"Response": "False", "Error": "..."} on failure
        if body.get("Response") == "False":
            err = body.get("Error", "unknown error")
            logger.warning("OMDB %s — %s", title, err)
            return None

        return body
    except URLError:
        logger.exception(
            "OMDB request for %r — network error (check internet / proxy / firewall)",
            title,
        )
        return None
    except Exception:
        logger.exception("OMDB request for %r failed", title)
        return None


def _omdb_get_by_imdb_id(
    imdb_id: str,
    api_key: str,
) -> dict[str, object] | None:
    """Query OMDB by IMDb ID (``?i=`` parameter).

    Returns the parsed JSON body on success, or ``None`` on error.
    """
    try:
        params: dict[str, str] = {"apikey": api_key, "i": imdb_id}
        url = f"{OMDB_API_BASE}/?{urlencode(params)}"
        req = Request(url, headers={"Accept": "application/json"})
        resp = urlopen(req, timeout=10)

        if resp.status != 200:
            logger.warning("OMDB i= lookup %s returned %s", imdb_id, resp.status)
            return None

        body: dict[str, object] = json.loads(resp.read().decode("utf-8"))

        if body.get("Response") == "False":
            err = body.get("Error", "unknown error")
            logger.warning("OMDB i= lookup %s — %s", imdb_id, err)
            return None

        return body
    except URLError:
        logger.exception(
            "OMDB i= lookup %r — network error (check internet / proxy / firewall)",
            imdb_id,
        )
        return None
    except Exception:
        logger.exception("OMDB i= lookup %r failed", imdb_id)
        return None


def _omdb_search(
    title: str,
    year: int | None,
    api_key: str,
    type_: str | None = None,
) -> list[dict[str, object]] | None:
    """Search OMDB for movies matching *title* and optional *year*.

    *type_* — optional OMDB ``type`` filter.

    Returns a list of result dicts (each containing at least ``Title``,
    ``Year``, ``imdbID``, ``Poster``), or ``None`` if no results.
    """
    body = _omdb_get(title, year, api_key, exact=False, type_=type_)
    if body is None:
        return None

    raw_results: object = body.get("Search")
    if raw_results is None:
        return None

    results = cast(list[dict[str, object]], raw_results)
    return results if results else None


def _extract_poster(result: dict[str, object]) -> str | None:
    """Extract a poster URL from an OMDB result dict.

    OMDB returns ``"N/A"`` when no poster is available.
    """
    raw: object = result.get("Poster", "N/A")
    poster = cast(str, raw)
    if poster and poster != "N/A":
        return poster
    return None
