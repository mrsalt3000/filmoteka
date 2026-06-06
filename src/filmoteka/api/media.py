"""Media endpoints: stream video files for playback."""

# ruff: noqa: B008  FastAPI requires Depends() in function signatures

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from filmoteka.api.auth import _get_current_user
from filmoteka.api.schemas.watch import (
    WatchProgressRequest,
    WatchStartResponse,
    WatchStateResponse,
)
from filmoteka.domain.access.models import User
from filmoteka.domain.catalog.models import MediaFile
from filmoteka.domain.watching.models import WatchEvent
from filmoteka.infrastructure.database import get_db

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{media_id}/stream")
def stream_media(
    media_id: int,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Stream a media file by its ID.

    Supports Range headers for seeking (handled by ``FileResponse``).
    """
    media = db.get(MediaFile, media_id)
    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found",
        )

    path = Path(media.file_path)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found on disk",
        )

    return FileResponse(
        path=path,
        filename=path.name,
        media_type="video/mp4",
    )


@router.get("/{media_id}/watch/state", response_model=WatchStateResponse)
def watch_state(
    media_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> WatchStateResponse:
    """Return the current watch state for a media file.

    If an unfinished ``WatchEvent`` exists, returns it with the last
    position so the client can offer resume.  No side effects.
    """
    event = (
        db.query(WatchEvent)
        .filter(
            WatchEvent.media_file_id == media_id,
            WatchEvent.user_id == current_user.id,
            WatchEvent.finished == False,  # noqa: E712
        )
        .first()
    )
    if event is None:
        return WatchStateResponse(has_state=False)

    return WatchStateResponse(
        has_state=True,
        watch_event_id=event.id,
        media_file_id=event.media_file_id,
        started_at=event.started_at,
        last_position=event.last_position,
        finished=event.finished,
    )


@router.post("/{media_id}/watch/start", response_model=WatchStartResponse)
def start_watch(
    media_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> WatchStartResponse:
    """Start or resume watching a media file.

    Creates a new ``WatchEvent`` if none exists for this user and media file.
    If an unfinished ``WatchEvent`` already exists, returns it so the client
    can resume from ``last_position``.
    """
    media = db.get(MediaFile, media_id)
    if media is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found",
        )

    # Look for an existing unfinished watch event (resume).
    existing = (
        db.query(WatchEvent)
        .filter(
            WatchEvent.media_file_id == media_id,
            WatchEvent.user_id == current_user.id,
            WatchEvent.finished == False,  # noqa: E712
        )
        .first()
    )
    if existing is not None:
        return WatchStartResponse(
            watch_event_id=existing.id,
            media_file_id=existing.media_file_id,
            started_at=existing.started_at,
            last_position=existing.last_position,
            finished=existing.finished,
        )

    event = WatchEvent(media_file_id=media_id, user_id=current_user.id)
    db.add(event)
    db.commit()
    db.refresh(event)

    return WatchStartResponse(
        watch_event_id=event.id,
        media_file_id=event.media_file_id,
        started_at=event.started_at,
        last_position=event.last_position,
        finished=event.finished,
    )


@router.patch("/{media_id}/watch/{watch_event_id}/progress")
def update_progress(
    media_id: int,
    watch_event_id: int,
    body: WatchProgressRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> dict[str, str]:
    """Update playback position for a watch event."""
    event = db.get(WatchEvent, watch_event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Watch event not found",
        )
    if event.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Watch event belongs to another user",
        )

    event.last_position = body.position
    db.flush()

    return {"status": "ok"}
