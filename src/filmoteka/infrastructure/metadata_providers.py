"""External metadata provider layer — OMDB poster search.

V1 scope: poster search via OMDB API (www.omdbapi.com).
External data is unreliable; always store source and confidence
for later review (V1-005).
"""

from __future__ import annotations

import json
import logging
from typing import cast
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

OMDB_API_BASE = "http://www.omdbapi.com"


# ---------------------------------------------------------------------------
# Poster search
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
) -> dict[str, object] | None:
    """Query OMDB by title.

    If *exact* is ``True``, uses ``?t=`` parameter (single result).
    Otherwise uses ``?s=`` parameter (search, returns list).

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


def _omdb_search(
    title: str,
    year: int | None,
    api_key: str,
) -> list[dict[str, object]] | None:
    """Search OMDB for movies matching *title* and optional *year*.

    Returns a list of result dicts (each containing at least ``Title``,
    ``Year``, ``imdbID``, ``Poster``), or ``None`` if no results.
    """
    body = _omdb_get(title, year, api_key, exact=False)
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
