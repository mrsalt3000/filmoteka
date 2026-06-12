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
