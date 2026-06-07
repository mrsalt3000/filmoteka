"""External metadata provider layer — TMDb, LLM, etc.

V1 scope: poster search via TMDb API. External data is unreliable;
always store source and confidence for later review (V1-005).
"""

from __future__ import annotations

import json
import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"


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
    try:
        params = {"api_key": api_key, "query": title, "language": "en-US"}
        if year is not None:
            params["year"] = str(year)

        url = f"{TMDB_API_BASE}/search/movie?{urlencode(params)}"
        req = Request(url, headers={"Accept": "application/json"})
        resp = urlopen(req, timeout=10)

        if resp.status != 200:
            logger.warning("TMDb search returned %s for title=%r", resp.status, title)
            return None

        body = json.loads(resp.read().decode("utf-8"))
        results = body.get("results") or []
        if not results:
            return None

        poster_path = results[0].get("poster_path")
        if not poster_path:
            return None

        poster_url = f"{TMDB_IMAGE_BASE}/w500{poster_path}"
        logger.info("TMDb poster found for %r: %s", title, poster_url)
        return (poster_url, "tmdb")

    except Exception:
        logger.exception("TMDb poster search failed for title=%r", title)
        return None
