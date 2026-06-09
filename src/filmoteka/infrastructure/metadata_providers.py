"""External metadata provider layer — TMDb, LLM, etc.

V1 scope: poster search via TMDb API, Kinopoisk external links.
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

TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tmdb_api_get(
    path: str, api_key: str, params: dict[str, str] | None = None
) -> dict[str, object] | None:
    """Perform a GET request against the TMDb API.

    Returns the parsed JSON body on success (HTTP 200), or ``None`` on
    any error.  This is best-effort — all exceptions are caught and
    logged.
    """
    try:
        query: dict[str, str] = {"api_key": api_key, **(params or {})}
        url = f"{TMDB_API_BASE}{path}?{urlencode(query)}"
        req = Request(url, headers={"Accept": "application/json"})
        resp = urlopen(req, timeout=10)

        if resp.status != 200:
            logger.warning("TMDb GET %s returned %s", path, resp.status)
            return None

        body: dict[str, object] = json.loads(resp.read().decode("utf-8"))
        return body
    except URLError:
        logger.exception(
            "TMDb GET %s — network error (check internet / proxy / firewall), "
            "see https://github.com/mrsalt3000/filmoteka#troubleshooting",
            path,
        )
        return None
    except Exception:
        logger.exception("TMDb GET %s failed", path)
        return None


def _tmdb_search_first(
    title: str, year: int | None, api_key: str
) -> dict[str, object] | None:
    """Search TMDb for a movie by *title* and optional *year*.

    Returns the first result dict (which includes keys like ``id``,
    ``poster_path``, ``title``, ``release_date``), or ``None`` if no
    results are found.
    """
    params: dict[str, str] = {"query": title, "language": "en-US"}
    if year is not None:
        params["year"] = str(year)

    body = _tmdb_api_get("/search/movie", api_key, params)
    if body is None:
        return None

    raw_results: object = body.get("results") or []
    results = cast(list[dict[str, object]], raw_results)
    return results[0] if results else None


# ---------------------------------------------------------------------------
# Poster search
# ---------------------------------------------------------------------------


def tmdb_search_poster(
    title: str,
    year: int | None,
    api_key: str,
) -> tuple[str, str] | None:
    """Search TMDb for a poster URL matching *title* and optional *year*.

    Returns ``(poster_url, source)`` on success, or ``None`` if no poster
    is found.  The source string is ``"tmdb"``.

    This is best-effort — network errors, missing results, or invalid API
    keys are logged and return ``None`` rather than raising.
    """
    result = _tmdb_search_first(title, year, api_key)
    if result is None:
        return None

    raw_path: object = result.get("poster_path")
    poster_path = cast(str | None, raw_path)
    if not poster_path:
        return None

    poster_url = f"{TMDB_IMAGE_BASE}/w500{poster_path}"
    logger.info("TMDb poster found for %r: %s", title, poster_url)
    return (poster_url, "tmdb")


# ---------------------------------------------------------------------------
# External links — Kinopoisk
# ---------------------------------------------------------------------------


KINOPOISK_URL_TEMPLATE = "https://www.kinopoisk.ru/film/{kp_id}/"


def tmdb_find_kinopoisk_url(
    title: str,
    year: int | None,
    api_key: str,
) -> str | None:
    """Search TMDb for a Kinopoisk URL matching *title* and optional *year*.

    Returns the full ``https://www.kinopoisk.ru/film/{id}/`` URL, or
    ``None`` if no match is found.

    Best-effort — errors and missing data are logged and return ``None``.
    """
    result = _tmdb_search_first(title, year, api_key)
    if result is None:
        return None

    raw_id: object = result.get("id", 0)
    tmdb_id = cast(int, raw_id)
    if tmdb_id == 0:
        return None

    ext = _tmdb_api_get(f"/movie/{tmdb_id}/external_ids", api_key)
    if ext is None:
        return None

    raw_kp: object = ext.get("kp_id")
    kp_id = cast(int | None, raw_kp)
    if kp_id is None:
        return None

    url = KINOPOISK_URL_TEMPLATE.format(kp_id=kp_id)
    logger.info("Kinopoisk URL found for %r: %s", title, url)
    return url
