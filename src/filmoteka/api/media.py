"""Media endpoints: stream video files for playback."""

# ruff: noqa: B008  FastAPI requires Depends() in function signatures

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from filmoteka.domain.catalog.models import MediaFile
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
