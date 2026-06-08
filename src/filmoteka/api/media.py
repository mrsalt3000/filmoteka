"""Media endpoints: stream video files for playback."""

# ruff: noqa: B008  FastAPI requires Depends() in function signatures

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Generator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload

from filmoteka.api.auth import _get_current_user
from filmoteka.api.schemas.watch import (
    FilmWatchState,
    FilmWatchStatesRequest,
    FilmWatchStatesResponse,
    WatchProgressRequest,
    WatchStartResponse,
    WatchStateResponse,
)
from filmoteka.domain.access.models import User
from filmoteka.domain.catalog.models import Film, MediaFile, MovieEdition
from filmoteka.domain.watching.models import WatchEvent
from filmoteka.infrastructure.database import get_db

router = APIRouter(prefix="/media", tags=["media"])

# ---------------------------------------------------------------------------
# MIME type helpers
# ---------------------------------------------------------------------------

_MIME_MAP: dict[str, str] = {
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mov": "video/quicktime",
    ".m4v": "video/mp4",
    ".ogv": "video/ogg",
    ".ts": "video/mp2t",
}


def _mime_type(suffix: str) -> str:
    """Return the MIME type for a given file extension suffix."""
    return _MIME_MAP.get(suffix.lower(), "application/octet-stream")


def _ffmpeg_available() -> bool:
    """Return ``True`` if ``ffmpeg`` is found on ``PATH``."""
    return shutil.which("ffmpeg") is not None


# ---------------------------------------------------------------------------
# FFmpeg remux streaming
# ---------------------------------------------------------------------------


def _ffmpeg_remux_stream(path: Path) -> StreamingResponse:
    """Remux *path* (typically .mkv) to fragmented MP4 via ffmpeg.

    Uses stream copy (no re-encoding) so it is fast and lossless.
    The output is a fragmented MP4 that browsers can play progressively.
    """

    def generate() -> Generator[bytes, None, None]:
        cmd = [
            "ffmpeg",
            "-i", str(path),
            "-c", "copy",
            "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "pipe:1",
        ]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        try:
            stdout = process.stdout
            if stdout is None:
                return
            while True:
                chunk = stdout.read(65536)
                if not chunk:
                    break
                yield chunk
        finally:
            process.terminate()
            process.wait()

    return StreamingResponse(
        generate(),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f'inline; filename="{path.stem}.mp4"',
            "Accept-Ranges": "none",
        },
    )


# ---------------------------------------------------------------------------
# Stream endpoint
# ---------------------------------------------------------------------------


@router.api_route("/{media_id}/stream", methods=["GET", "HEAD"], response_model=None)
def stream_media(
    media_id: int,
    request: Request,
    db: Session = Depends(get_db),
) -> FileResponse | Response | StreamingResponse:
    """Stream a media file by its ID.

    Supports two HTTP methods:

    - **HEAD**: returns headers only (no body) for availability checks.
    - **GET**: returns the media content.

    For native browser formats (MP4, WebM) the file is served via
    ``FileResponse`` with native Range-header seek support.

    For MKV files, if ``ffmpeg`` is available on ``PATH``, the file is
    remuxed to fragmented MP4 on the fly (stream copy, no re-encode)
    via ``StreamingResponse``.  Range-header seeking is not supported
    in this mode.

    If MKV and ffmpeg is not available, returns 415 Unsupported Media
    Type.
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

    suffix = path.suffix.lower()
    mime = _mime_type(suffix)

    # MKV without ffmpeg is unsupported
    if suffix == ".mkv" and not _ffmpeg_available():
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="MKV format is not supported in browser",
        )

    # HEAD — return minimal headers without body
    if request.method == "HEAD":
        return Response(
            headers={
                "Content-Type": mime,
                "Accept-Ranges": "none" if suffix == ".mkv" else "bytes",
            },
        )

    # MKV with ffmpeg — streaming remux
    if suffix == ".mkv":
        return _ffmpeg_remux_stream(path)

    # All other formats — standard FileResponse with Range support
    return FileResponse(
        path=path,
        filename=path.name,
        media_type=mime,
    )


@router.post("/watch/states-by-film", response_model=FilmWatchStatesResponse)
def watch_states_by_film(
    body: FilmWatchStatesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> FilmWatchStatesResponse:
    """Return watch states for a batch of films (keyed by film_id).

    For each film_id, finds the first MediaFile (via editions) and
    returns the current user's watch state if an unfinished event exists.
    """
    if not body.film_ids:
        return FilmWatchStatesResponse(states={})

    # Fetch all films with their editions and media files in one query
    films = (
        db.query(Film)
        .options(
            joinedload(Film.editions).joinedload(MovieEdition.media_files),
        )
        .filter(Film.id.in_(body.film_ids))
        .all()
    )

    # Collect media_file_id -> film_id mapping
    media_to_film: dict[int, int] = {}
    for f in films:
        for ed in f.editions:
            for mf in ed.media_files:
                if mf.id not in media_to_film:
                    media_to_film[mf.id] = f.id
                break  # first media file per edition is enough
            break  # first edition is enough

    if not media_to_film:
        # No media files found — all films have no state
        return FilmWatchStatesResponse(
            states={str(f.id): FilmWatchState(has_state=False) for f in films}
        )

    # Fetch all unfinished watch events for these media files in one query
    events = (
        db.query(WatchEvent)
        .filter(
            WatchEvent.media_file_id.in_(list(media_to_film.keys())),
            WatchEvent.user_id == current_user.id,
            WatchEvent.finished == False,  # noqa: E712
        )
        .all()
    )

    # Build media_id -> WatchEvent mapping
    event_by_media: dict[int, WatchEvent] = {e.media_file_id: e for e in events}

    # Build result keyed by film_id (as string for JSON dict)
    states: dict[str, FilmWatchState] = {}
    for f in films:
        media_id = None
        duration_secs = None
        for ed in f.editions:
            for mf in ed.media_files:
                media_id = mf.id
                duration_secs = mf.duration_secs
                break
            if media_id is not None:
                break

        if media_id is None or media_id not in event_by_media:
            states[str(f.id)] = FilmWatchState(has_state=False)
        else:
            ev = event_by_media[media_id]
            states[str(f.id)] = FilmWatchState(
                has_state=True,
                last_position=ev.last_position,
                duration_secs=duration_secs,
                finished=ev.finished,
            )

    return FilmWatchStatesResponse(states=states)


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
    db.commit()

    return {"status": "ok"}
