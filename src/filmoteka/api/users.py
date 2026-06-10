"""User-specific endpoints: profile, watch history, blacklist."""

# ruff: noqa: B008  FastAPI requires Depends() in function signatures

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from filmoteka.api.auth import _get_current_user
from filmoteka.api.schemas.watch import WatchHistoryItem, WatchHistoryResponse
from filmoteka.domain.access.models import User, UserFilmBlacklist
from filmoteka.domain.catalog.models import Film, MediaFile, MovieEdition
from filmoteka.domain.watching.models import WatchEvent
from filmoteka.infrastructure.database import get_db

router = APIRouter(prefix="/me", tags=["users"])


class BlacklistResponse(BaseModel):
    film_ids: list[int]


@router.get("/blacklist", response_model=BlacklistResponse)
def list_blacklist(
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> BlacklistResponse:
    """Return the list of film IDs the current user has blacklisted."""
    rows = (
        db.query(UserFilmBlacklist.film_id)
        .filter(UserFilmBlacklist.user_id == current_user.id)
        .all()
    )
    return BlacklistResponse(film_ids=[r[0] for r in rows])


@router.post("/blacklist/{film_id}", status_code=204)
def add_to_blacklist(
    film_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> None:
    """Add a film to the current user's blacklist."""
    film = db.get(Film, film_id)
    if film is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Film not found",
        )

    existing = (
        db.query(UserFilmBlacklist)
        .filter(
            UserFilmBlacklist.user_id == current_user.id,
            UserFilmBlacklist.film_id == film_id,
        )
        .first()
    )
    if existing is not None:
        return  # already blacklisted — idempotent

    db.add(UserFilmBlacklist(user_id=current_user.id, film_id=film_id))
    db.commit()


@router.delete("/blacklist/{film_id}", status_code=204)
def remove_from_blacklist(
    film_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> None:
    """Remove a film from the current user's blacklist."""
    entry = (
        db.query(UserFilmBlacklist)
        .filter(
            UserFilmBlacklist.user_id == current_user.id,
            UserFilmBlacklist.film_id == film_id,
        )
        .first()
    )
    if entry is None:
        return  # not blacklisted — idempotent

    db.delete(entry)
    db.commit()


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
