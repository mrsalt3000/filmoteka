"""User-specific endpoints: profile, watch history."""

# ruff: noqa: B008  FastAPI requires Depends() in function signatures

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

from filmoteka.api.auth import _get_current_user
from filmoteka.api.schemas.watch import WatchHistoryItem, WatchHistoryResponse
from filmoteka.domain.access.models import User
from filmoteka.domain.catalog.models import MediaFile, MovieEdition
from filmoteka.domain.watching.models import WatchEvent
from filmoteka.infrastructure.database import get_db

router = APIRouter(prefix="/me", tags=["users"])


@router.get("/watch/history", response_model=WatchHistoryResponse)
def watch_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> WatchHistoryResponse:
    """Return a paginated list of watch events for the current user."""
    query = (
        db.query(WatchEvent)
        .options(
            joinedload(WatchEvent.media_file)
            .joinedload(MediaFile.edition)
            .joinedload(MovieEdition.film)
        )
        .filter(WatchEvent.user_id == current_user.id)
    )

    total = query.count()
    events = (
        query.order_by(WatchEvent.started_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = [
        WatchHistoryItem(
            watch_event_id=e.id,
            media_file_id=e.media_file_id,
            film_id=e.media_file.edition.film.id,
            film_title=e.media_file.edition.film.title,
            film_year=e.media_file.edition.film.year,
            started_at=e.started_at,
            last_position=e.last_position,
            finished=e.finished,
        )
        for e in events
    ]

    return WatchHistoryResponse(items=items, total=total)
