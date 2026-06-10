"""Public health/info endpoints — no auth required."""

from __future__ import annotations

from urllib.request import Request, urlopen

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.orm import Session

from filmoteka.api.schemas.watch import ComponentStatus, HealthResponse
from filmoteka.infrastructure.database import SessionLocal
from filmoteka.infrastructure.settings import settings

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return overall service health.

    Checks database connectivity and (briefly) external service
    reachability.  Designed for load balancer / docker health checks.
    """
    # Database check
    db_status = "ok"
    try:
        db: Session = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:
        db_status = "degraded"

    # External connectivity check (OMDB — 3s timeout)
    ext_status = "ok"
    if settings.omdb_api_key:
        try:
            url = f"http://www.omdbapi.com/?apikey={settings.omdb_api_key}&s=test"
            req = Request(url, headers={"Accept": "application/json"})
            resp = urlopen(req, timeout=3)
            if resp.status != 200:
                ext_status = "degraded"
        except Exception:
            ext_status = "unavailable"

    overall = "ok" if db_status == "ok" else "degraded"

    return HealthResponse(
        status=overall,
        database=ComponentStatus(status=db_status),
        external=ComponentStatus(status=ext_status),
        version="2.0.0",
    )
