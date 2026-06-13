"""Public health/info endpoints — no auth required.

* ``GET /health/live`` — trivial liveness probe (always 200).
* ``GET /health`` — readiness probe (checks DB, Redis, and OMDB).
"""

from __future__ import annotations

import logging
from urllib.request import Request, urlopen

from fastapi import APIRouter
from redis import Redis as RedisClient
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.orm import Session

from filmoteka.api.schemas.watch import ComponentStatus, HealthResponse
from filmoteka.infrastructure.database import SessionLocal
from filmoteka.infrastructure.settings import settings

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health/live")
def health_live() -> dict[str, str]:
    """Trivial liveness probe — always returns 200 while the process is alive."""
    return {"status": "ok"}


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return overall service readiness — checks DB, Redis, and OMDB."""
    # ── Database ──
    db_status = "ok"
    try:
        db: Session = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception as exc:
        _logger.warning("Health check — database: %s", exc)
        db_status = "degraded"

    # ── Redis ──
    redis_status = "ok"
    try:
        client = RedisClient.from_url(str(settings.redis_url))
        client.ping()
        client.close()
    except (RedisError, Exception) as exc:
        _logger.warning("Health check — redis: %s", exc)
        redis_status = "degraded"

    # ── OMDB (external) ──
    ext_status = "ok"
    if settings.omdb_api_key:
        try:
            url = f"http://www.omdbapi.com/?apikey={settings.omdb_api_key}&s=test"
            req = Request(url, headers={"Accept": "application/json"})
            resp = urlopen(req, timeout=3)
            if resp.status != 200:
                ext_status = "degraded"
        except Exception as exc:
            _logger.warning("Health check — OMDB: %s", exc)
            ext_status = "unavailable"

    overall = "ok" if db_status == "ok" else "degraded"

    return HealthResponse(
        status=overall,
        database=ComponentStatus(status=db_status),
        redis=ComponentStatus(status=redis_status),
        external=ComponentStatus(status=ext_status),
        version="2.0.0",
    )
