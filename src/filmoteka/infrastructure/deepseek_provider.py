"""DeepSeek API client for metadata enrichment.

Uses the DeepSeek chat completions endpoint to extract structured
metadata (genre, description, actors, country) from a film title.
Gracefully degrades when the API key is missing or the service is
unreachable — returns ``None`` instead of raising.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from filmoteka.infrastructure.metadata_providers import clean_title_for_omdb

logger = logging.getLogger(__name__)

DEEPSEEK_API_BASE = "https://api.deepseek.com"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class DeepSeekEnrichmentResult:
    """Structured metadata extracted by DeepSeek for a film."""

    def __init__(
        self,
        genres: list[str] | None = None,
        description: str | None = None,
        actors: list[str] | None = None,
        country: str | None = None,
    ) -> None:
        self.genres = genres or []
        self.description = description
        self.actors = actors or []
        self.country = country


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def deepseek_enrich_metadata(
    title: str,
    year: int | None,
    api_key: str,
) -> DeepSeekEnrichmentResult | None:
    """Query DeepSeek for structured metadata about *title* (optional *year*).

    Returns a ``DeepSeekEnrichmentResult`` on success, or ``None`` if the
    API is unreachable, returns an error, or the response cannot be parsed.

    This is best-effort — network errors, rate limits, or invalid keys
    are logged and return ``None``.
    """
    year_str = f" ({year})" if year else ""
    film_label = f"{title}{year_str}"

    system_prompt = (
        "You are a film metadata assistant. Given a movie title and optional year, "
        "return a JSON object with exactly these fields:\n"
        "- \"genres\": array of strings (max 5 genre names in English,\n"
        '  e.g. ["Action", "Drama"])\n'
        "- \"description\": string (1-3 sentences plot summary in English)\n"
        "- \"actors\": array of strings (max 5 main actor names)\n"
        "- \"country\": string or null (production country in English,\n"
        '  e.g. "USA", "France")\n\n'
        "Respond with ONLY the JSON object, no markdown, no explanation."
    )

    user_prompt = f"Movie: {film_label}"

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 500,
    }

    try:
        req = Request(
            f"{DEEPSEEK_API_BASE}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        resp = urlopen(req, timeout=30)

        if resp.status != 200:
            logger.warning("DeepSeek returned %s for %r", resp.status, film_label)
            return None

        raw: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except URLError:
        logger.exception("DeepSeek network error for %r", film_label)
        return None
    except json.JSONDecodeError:
        logger.exception("DeepSeek returned invalid JSON for %r", film_label)
        return None
    except Exception:
        logger.exception("DeepSeek request failed for %r", film_label)
        return None

    # Extract the assistant message content
    content: str | None = None
    try:
        choices = raw.get("choices", [])
        if not choices:
            logger.warning("DeepSeek returned empty choices for %r", film_label)
            return None

        message = choices[0].get("message", {})
        content = message.get("content")
        if not content:
            logger.warning("DeepSeek returned empty message content for %r", film_label)
            return None

        # Parse the JSON from the content
        # DeepSeek may wrap in markdown ```json ... ```
        content_stripped = content.strip()
        if content_stripped.startswith("```"):
            # Extract JSON from markdown code block
            for line in content_stripped.split("\n"):
                stripped = line.strip()
                if stripped == "```json" or stripped == "```":
                    continue
                if stripped.endswith("```"):
                    content_stripped = stripped[:-3].strip()
                    break
            else:
                # Fallback: try to find JSON after the first ```
                start = content_stripped.find("\n")
                end = content_stripped.rfind("```")
                if start != -1 and end != -1:
                    content_stripped = content_stripped[start:end].strip()

        data: dict[str, Any] = json.loads(content_stripped)
    except (KeyError, IndexError, json.JSONDecodeError, TypeError):
        snippet = (content[:200] + "...") if content else "empty"
        logger.exception(
            "DeepSeek response parse failed for %r — response: %s",
            film_label, snippet,
        )
        return None

    genres_raw: object = data.get("genres", [])
    actors_raw: object = data.get("actors", [])

    result = DeepSeekEnrichmentResult(
        genres=[str(g) for g in (genres_raw if isinstance(genres_raw, list) else [])],
        description=str(data["description"]) if data.get("description") else None,
        actors=[str(a) for a in (actors_raw if isinstance(actors_raw, list) else [])],
        country=str(data["country"]) if data.get("country") and data["country"] != "null" else None,
    )

    logger.info(
        "DeepSeek enrichment for %r: %d genres, %d actors, country=%s",
        film_label, len(result.genres), len(result.actors), result.country,
    )
    return result


# ---------------------------------------------------------------------------
# Media file alias generation
# ---------------------------------------------------------------------------


def deepseek_generate_alias(file_stem: str, api_key: str) -> str | None:
    """Generate a human-readable alias for a media file from its *file_stem*.

    The *file_stem* is the filename without extension or path
    (e.g. ``"Брат.1997.WEB-DLRip-AVC_[New-team]_by_AVP_Studio"``).

    Returns a clean alias like ``"Брат (1997)"``, or ``None`` if the LLM
    is unreachable or returns an invalid response (graceful degradation).
    """
    system_prompt = (
        "You are a film filename parser. Given a movie filename (without extension), "
        "extract the movie title and year. Return ONLY the title and year in the format:\n"
        '"Title (Year)"\n\n'
        "Examples:\n"
        '- "Брат.1997.WEB-DLRip-AVC_[New-team]_by_AVP_Studio" → "Брат (1997)"\n'
        '- "The.Matrix.1999.1080p.BluRay.x264" → "The Matrix (1999)"\n'
        '- "Inception.2010.1080p" → "Inception (2010)"\n'
        '- "My.Family.Vacation.2021" → "My Family Vacation (2021)"\n\n'
        "Respond with ONLY the formatted title, no explanation, no extra text."
    )

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": file_stem},
        ],
        "temperature": 0.1,
        "max_tokens": 100,
    }

    try:
        req = Request(
            f"{DEEPSEEK_API_BASE}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        resp = urlopen(req, timeout=30)

        if resp.status != 200:
            logger.warning("DeepSeek alias generation returned %s", resp.status)
            return None

        raw: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except Exception:
        logger.exception("DeepSeek alias generation failed for %r", file_stem)
        return None

    try:
        content: str = raw["choices"][0]["message"]["content"]
        # Strip whitespace, quotes, markdown code fences
        alias = content.strip().strip('"').strip("'").strip("`")
        # Remove markdown ``` if present
        if alias.startswith("```"):
            alias = alias.split("\n")[-1] if "\n" in alias else alias.replace("```", "")
        alias = alias.strip().strip('"').strip("'")
        if alias:
            logger.info("DeepSeek alias for %r → %r", file_stem, alias)
            return alias
    except (KeyError, IndexError, TypeError):
        logger.exception("DeepSeek alias parse failed for %r", file_stem)

    return None


# ---------------------------------------------------------------------------
# Structured search info extraction (title + year + type)
# ---------------------------------------------------------------------------


_SEARCH_INFO_SYSTEM_PROMPT = (
    "You are a film filename parser. Given a media filename (without extension), "
    "extract the title, year, and content type. "
    "Return ONLY a JSON object with these fields, no markdown, no explanation:\n"
    "{\n"
    '  "title": "extracted movie or show title",\n'
    '  "year": <4-digit year or null if unknown>,\n'
    '  "type": "movie" or "series" or "episode" or null\n'
    "}\n\n"
    "Guidelines:\n"
    '- "movie": feature films, documentaries, standalone content\n'
    '- "series": TV series, mini-series, TV shows (any multi-episode format)\n'
    '- "episode": individual episode of a series (has SxxExx pattern)\n'
    "- null: unable to determine\n\n"
    "Examples:\n"
    '- "The.Matrix.1999.1080p.BluRay.x264" → {"title": "The Matrix", "year": 1999, "type": "movie"}\n'  # noqa: E501
    '- "Gravity.Falls.S01E01.IVI.SOFCI" → {"title": "Gravity Falls", "year": 2012, "type": "series"}\n'  # noqa: E501
    '- "The.Mandalorian.S02E03.Chapter.11.2160p" → {"title": "The Mandalorian", "year": 2020, "type": "series"}\n'  # noqa: E501
    '- "Inception.2010.1080p" → {"title": "Inception", "year": 2010, "type": "movie"}\n'
    '- "My.Family.Vacation.2021.HDRip" → {"title": "My Family Vacation", "year": 2021, "type": "movie"}\n'  # noqa: E501
    '- "UFC.300.Main.Card.PPV.1080p" → {"title": "UFC 300", "year": 2024, "type": "movie"}\n'
)


def deepseek_extract_search_info(
    file_stem: str,
    api_key: str,
) -> dict[str, Any] | None:
    """Extract structured search info from a media filename via DeepSeek.

    Returns a dict with keys:
    - ``title`` (str) — cleaned title suitable for OMDB search
    - ``year`` (int | None) — extracted year
    - ``type`` (str | None) — ``"movie"``, ``"series"``, or ``None``

    Falls back to :func:`clean_title_for_omdb` when DeepSeek is unavailable
    or returns an invalid response (``type`` will be ``None`` on fallback).
    """
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": _SEARCH_INFO_SYSTEM_PROMPT},
            {"role": "user", "content": file_stem},
        ],
        "temperature": 0.1,
        "max_tokens": 150,
    }

    try:
        req = Request(
            f"{DEEPSEEK_API_BASE}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        resp = urlopen(req, timeout=30)

        if resp.status != 200:
            logger.warning("DeepSeek search info returned %s", resp.status)
            return _fallback_search_info(file_stem)

        raw: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
    except Exception:
        logger.exception("DeepSeek search info failed for %r", file_stem)
        return _fallback_search_info(file_stem)

    try:
        content: str = raw["choices"][0]["message"]["content"]
        if not content:
            logger.warning("DeepSeek search info returned empty content for %r", file_stem)
            return _fallback_search_info(file_stem)

        # Strip markdown code fences
        text = content.strip()
        if text.startswith("```"):
            for line in text.split("\n"):
                stripped = line.strip()
                if stripped in ("```json", "```", ""):
                    continue
                if stripped.endswith("```"):
                    text = stripped[:-3].strip()
                    break
            else:
                start = text.find("\n")
                end = text.rfind("```")
                if start != -1 and end != -1:
                    text = text[start:end].strip()

        data: dict[str, Any] = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError, TypeError):
        snippet = (content[:200] + "...") if content else "empty"
        logger.exception(
            "DeepSeek search info parse failed for %r — response: %s",
            file_stem, snippet,
        )
        return _fallback_search_info(file_stem)

    title = data.get("title")
    if not title or not isinstance(title, str):
        logger.warning("DeepSeek search info missing title for %r", file_stem)
        return _fallback_search_info(file_stem)

    year: int | None = data.get("year")
    if year is not None:
        try:
            year = int(year)
        except (ValueError, TypeError):
            year = None

    raw_type: Any = data.get("type")
    content_type: str | None = None
    if isinstance(raw_type, str) and raw_type.lower() in ("movie", "series", "episode"):
        content_type = raw_type.lower()

    result: dict[str, Any] = {
        "title": title,
        "year": year,
        "type": content_type,
    }
    logger.info(
        "DeepSeek search info for %r → %r", file_stem, result,
    )
    return result


def _fallback_search_info(file_stem: str) -> dict[str, Any]:
    """Fallback when DeepSeek is unavailable: use title cleaner heuristics."""
    cleaned = clean_title_for_omdb(file_stem)
    result: dict[str, Any] = {
        "title": cleaned.title,
        "year": cleaned.year,
        "type": None,
    }
    logger.info(
        "DeepSeek search info fallback for %r → %r", file_stem, result,
    )
    return result
