"""Admin-only endpoints."""

# ruff: noqa: B008  FastAPI requires Depends() in function signatures

from __future__ import annotations

import logging
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import false as sa_false
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from filmoteka.api.auth import require_role
from filmoteka.api.dependencies import get_library_config
from filmoteka.api.schemas.auth import (
    VALID_AGE_GROUPS,
    VALID_ROLES,
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    UserOut,
)
from filmoteka.api.schemas.catalog import (
    ConflictEditionItem,
    ConflictItem,
    ConflictListResponse,
    ConflictMediaItem,
    EditionOut,
    FilmDetailOut,
    FilmUpdateSchema,
    GenreOut,
    MediaFileOut,
    PersonOut,
)
from filmoteka.api.schemas.jobs import (
    BackupFileItem,
    BackupListResponse,
    DownloadSuggestionsResponse,
    JobListResponse,
    JobStatusResponse,
)
from filmoteka.api.schemas.watch import (
    AdminWatchStatItem,
    AdminWatchStatsResponse,
    AdminWatchStatsSummaryItem,
    AdminWatchStatsSummaryResponse,
)
from filmoteka.domain.access.models import User
from filmoteka.domain.access.service import hash_password
from filmoteka.domain.catalog.models import (
    Film,
    Genre,
    MediaFile,
    MovieEdition,
    Person,
    film_person,
)
from filmoteka.domain.importing.pipeline import run_import
from filmoteka.domain.tasks.models import (
    JOB_CANCELLED,
    JOB_COMPLETED,
    JOB_FAILED,
    BackgroundJob,
)
from filmoteka.domain.tasks.worker import run_background_job, should_stop
from filmoteka.domain.watching.models import WatchEvent
from filmoteka.infrastructure.database import SessionLocal, get_db
from filmoteka.infrastructure.library_config import LibraryConfig
from filmoteka.infrastructure.media_probe import MediaProbeError, probe_media
from filmoteka.infrastructure.metadata_providers import omdb_search_poster
from filmoteka.infrastructure.settings import settings

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# Test-addressable session factory for background jobs.
_background_session_factory = SessionLocal


@router.get("/health")
def admin_health(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, str]:
    """Simple admin-only health check."""
    return {"status": "ok", "role": current_user.role, "username": current_user.username}


# ---------------------------------------------------------------------------
# Unified job status polling
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> BackgroundJob:
    """Return the status and result of a background job."""
    job = db.get(BackgroundJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return job


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Return a paginated list of recent background jobs."""
    total = db.query(BackgroundJob).count()
    jobs = (
        db.query(BackgroundJob)
        .order_by(BackgroundJob.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {"items": jobs, "total": total}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(
    job_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Request cancellation of a running background job.

    Sets ``cancel_requested = True`` and transitions the job status to
    ``cancelled``.  The worker thread checks this flag periodically and
    stops when convenient.  Already-cancelled or completed jobs are
    idempotent — this is a no-op.
    """
    job = db.get(BackgroundJob, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    job.cancel_requested = True
    if job.status not in (JOB_CANCELLED, JOB_COMPLETED, JOB_FAILED):
        job.status = JOB_CANCELLED  # type: ignore[attr-defined]
        from datetime import datetime as _dt
        job.completed_at = _dt.now()
    db.commit()

    # Release scan guard if cancelling a scan job
    global _active_scan_job_id, _active_transcode_job_id  # noqa: PLW0603
    if job_id == _active_scan_job_id:
        _active_scan_job_id = None
    if job_id == _active_transcode_job_id:
        _active_transcode_job_id = None

    return {"status": "ok", "id": job.id, "job_status": job.status}


# ---------------------------------------------------------------------------
# Watch statistics
# ---------------------------------------------------------------------------


@router.get("/watch-stats", response_model=AdminWatchStatsResponse)
def admin_watch_stats(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Return a paginated list of all watch events across users.

    Incognito events are excluded. Sorted by most recent first.
    """
    query = (
        db.query(
            User.id.label("user_id"),
            User.username,
            Film.title,
            WatchEvent.started_at,
            WatchEvent.finished,
        )
        .select_from(WatchEvent)
        .join(User, WatchEvent.user_id == User.id)
        .join(MediaFile, WatchEvent.media_file_id == MediaFile.id)
        .join(MovieEdition, MediaFile.edition_id == MovieEdition.id)
        .join(Film, MovieEdition.film_id == Film.id)
        .filter(WatchEvent.incognito == sa_false())
    )

    total = query.count()
    rows = (
        query.order_by(WatchEvent.started_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = [
        AdminWatchStatItem(
            user_id=r[0],
            username=r[1],
            film_title=r[2],
            started_at=r[3],
            finished=r[4],
        )
        for r in rows
    ]

    return {"items": items, "total": total}


@router.delete("/watch-stats/{user_id}", status_code=204)
def admin_clear_user_stats(
    user_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    """Delete all non-incognito watch events for a specific user.

    Admin-only. Returns 404 if the user does not exist.
    """
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    db.query(WatchEvent).filter(
        WatchEvent.user_id == user_id,
        WatchEvent.incognito == sa_false(),
    ).delete(synchronize_session=False)
    db.commit()


@router.get("/watch-stats/summary", response_model=AdminWatchStatsSummaryResponse)
def admin_watch_stats_summary(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Return per-user summary: how many unique films each user has started.

    Incognito events are excluded.
    """
    subq = (
        db.query(
            WatchEvent.user_id,
            sa_func.count(WatchEvent.media_file_id.distinct()).label("films_started"),
        )
        .filter(WatchEvent.incognito == sa_false())
        .group_by(WatchEvent.user_id)
        .subquery()
    )

    summary = (
        db.query(User.id, User.username, subq.c.films_started)
        .outerjoin(subq, User.id == subq.c.user_id)
        .order_by(sa_func.coalesce(subq.c.films_started, 0).desc())
        .all()
    )

    items = [
        AdminWatchStatsSummaryItem(
            user_id=r[0],
            username=r[1],
            films_started=r[2] or 0,
        )
        for r in summary
    ]

    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# Download suggestions
# ---------------------------------------------------------------------------


@router.get("/recommendations/download", response_model=DownloadSuggestionsResponse)
def admin_download_suggestions(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Suggest films to download based on library genres.

    For the top 3 genres in the library, searches OMDB for notable films
    and filters out those already present. Requires ``OMDB_API_KEY``.
    """
    if not settings.omdb_api_key:
        return {"items": [], "total": 0}

    # 1. Find top 3 genres by film count
    top_genres = (
        db.query(Genre.name)
        .join(Film.genres)
        .group_by(Genre.name)
        .order_by(sa_func.count(Genre.id).desc())
        .limit(3)
        .all()
    )
    genre_names = [g[0] for g in top_genres]

    if not genre_names:
        return {"items": [], "total": 0}

    # 2. Search OMDB for each genre
    import json as _json
    from urllib.parse import urlencode
    from urllib.request import Request, urlopen

    existing_titles = {f.lower() for f, in db.query(Film.title).all()}
    suggestions: list[dict[str, object]] = []
    seen_titles: set[str] = set()

    for genre in genre_names:
        try:
            params = {"apikey": settings.omdb_api_key, "s": genre, "type": "movie"}
            url = f"http://www.omdbapi.com/?{urlencode(params)}"
            req = Request(url, headers={"Accept": "application/json"})
            resp = urlopen(req, timeout=10)
            if resp.status != 200:
                continue
            body: dict = _json.loads(resp.read().decode("utf-8"))
            if body.get("Response") != "True":
                continue
            results: list[dict] = body.get("Search", [])
            for r in results:
                title = r.get("Title", "")
                title_lower = title.lower()
                year = r.get("Year", "")
                if title_lower in existing_titles or title_lower in seen_titles:
                    continue
                seen_titles.add(title_lower)
                suggestions.append({
                    "title": title,
                    "year": year,
                    "poster": r.get("Poster") if r.get("Poster") != "N/A" else None,
                    "genre": genre,
                    "reason": f"Popular in {genre}",
                })
        except Exception:
            _logger.warning("OMDB search failed for genre %r", genre, exc_info=True)
            continue

    return {"items": suggestions[:30], "total": len(suggestions[:30])}


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


@router.post("/backup", status_code=202)
def admin_create_backup(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Create a PostgreSQL backup via ``pg_dump``.

    Runs in a background job. Poll ``GET /admin/jobs/{job_id}``
    for completion.  The backup file path is returned in ``result``.
    """
    job = run_background_job(
        "backup", _run_backup,
        session_factory=_background_session_factory,
    )
    return {"job_id": job.id, "status": "pending", "type": "backup"}


def _run_backup() -> dict | None:
    """Run pg_dump and save to backup_dir."""
    import os
    import subprocess
    from datetime import datetime

    backup_dir = Path(settings.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"filmoteka_{timestamp}.sql"
    filepath = backup_dir / filename

    # Parse database_url for pg_dump connection
    url = settings.database_url
    # postgresql://user:password@host:port/dbname
    parts = url.replace("postgresql://", "").split("@")
    user_pass = parts[0].split(":")
    host_db = parts[1].split("/")
    host_port = host_db[0].split(":")

    env = os.environ.copy()
    env["PGPASSWORD"] = user_pass[1]

    result = subprocess.run(
        [
            "pg_dump",
            "-h", host_port[0],
            "-p", host_port[1] if len(host_port) > 1 else "5432",
            "-U", user_pass[0],
            "-d", host_db[1],
            "-f", str(filepath),
            "--no-owner",
            "--no-acl",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr}")

    file_size = filepath.stat().st_size
    return {"file": str(filepath), "size_bytes": file_size, "rows": filename}


@router.get("/backups", response_model=BackupListResponse)
def admin_list_backups(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """List available backup files in the backup directory."""
    backup_dir = Path(settings.backup_dir)
    if not backup_dir.is_dir():
        return {"items": [], "total": 0}

    files: list[dict] = []
    for p in sorted(backup_dir.glob("*.sql"), key=lambda f: f.stat().st_mtime, reverse=True):
        stat = p.stat()
        files.append(BackupFileItem(
            filename=p.name,
            size_bytes=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime),
        ).model_dump())

    return {"items": files, "total": len(files)}


@router.post("/restore/{filename}", status_code=202)
def admin_restore_backup(
    filename: str,
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Restore a backup file via ``psql``.

    The *filename* must be a valid ``.sql`` file in the backup directory.
    Runs in a background job. Poll ``GET /admin/jobs/{job_id}``.
    """
    filepath = Path(settings.backup_dir) / filename
    if not filepath.is_file() or filepath.suffix != ".sql":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backup file '{filename}' not found",
        )

    job = run_background_job(
        "restore", _run_restore, filename,
        session_factory=_background_session_factory,
    )
    return {"job_id": job.id, "status": "pending", "type": "restore"}


def _run_restore(filename: str) -> dict | None:
    """Run psql to restore a backup file."""
    import os
    import subprocess

    filepath = Path(settings.backup_dir) / filename
    url = settings.database_url
    parts = url.replace("postgresql://", "").split("@")
    user_pass = parts[0].split(":")
    host_db = parts[1].split("/")
    host_port = host_db[0].split(":")

    env = os.environ.copy()
    env["PGPASSWORD"] = user_pass[1]

    with open(filepath) as f:
        result = subprocess.run(
            [
                "psql",
                "-h", host_port[0],
                "-p", host_port[1] if len(host_port) > 1 else "5432",
                "-U", user_pass[0],
                "-d", host_db[1],
            ],
            stdin=f,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )

    if result.returncode != 0:
        raise RuntimeError(f"psql restore failed: {result.stderr}")

    return {"file": filename, "status": "restored"}


@router.post("/users", response_model=UserOut, status_code=201)
def admin_create_user(
    body: AdminCreateUserRequest,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> User:
    """Create a new user with a specified role (user or child) and optional age_group.

    Admin-only. Returns the created user.
    """
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid role '{body.role}'. Allowed: {', '.join(sorted(VALID_ROLES))}",
        )

    if body.age_group is not None and body.age_group not in VALID_AGE_GROUPS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid age_group '{body.age_group}'. "
                f"Allowed: {', '.join(sorted(VALID_AGE_GROUPS))}"
            ),
        )

    existing = db.query(User).filter(User.username == body.username).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )

    user = User(
        username=body.username,
        hashed_password=hash_password(body.password),
        role=body.role,
        age_group=body.age_group,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def admin_update_user(
    user_id: int,
    body: AdminUpdateUserRequest,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> User:
    """Update a user's age_group. Admin-only."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if body.age_group is not None and body.age_group not in VALID_AGE_GROUPS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid age_group '{body.age_group}'. "
                f"Allowed: {', '.join(sorted(VALID_AGE_GROUPS))}"
            ),
        )

    user.age_group = body.age_group
    db.commit()
    db.refresh(user)
    return user


@router.post("/import/scan", status_code=202)
def import_scan(
    current_user: User = Depends(require_role("admin")),
    config: LibraryConfig = Depends(get_library_config),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Start a background library scan.

    Returns immediately with 202 and a ``job_id``. Poll
    ``GET /admin/jobs/{job_id}`` for completion.
    """
    global _active_scan_job_id  # noqa: PLW0603

    # Guard against concurrent scans
    if _active_scan_job_id is not None:
        existing = db.get(BackgroundJob, _active_scan_job_id)
        if existing is not None and existing.status == "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A scan is already in progress",
            )

    job = run_background_job(
        "import_scan", _run_import_job, config,
        session_factory=_background_session_factory,
    )
    _active_scan_job_id = job.id
    return {"job_id": job.id, "status": "pending", "type": "import_scan"}


def _run_import_job(config: LibraryConfig) -> dict | None:
    """Run import pipeline and return the import report dict."""
    global _active_scan_job_id  # noqa: PLW0603
    job_id = _active_scan_job_id or 0
    db = SessionLocal()
    try:
        report = run_import(config, db, should_stop_fn=lambda: should_stop(job_id, SessionLocal))
        return report.to_dict()
    finally:
        _active_scan_job_id = None
        db.close()


# ---------------------------------------------------------------------------
# Conflict resolution
# ---------------------------------------------------------------------------


@router.get("/conflicts", response_model=ConflictListResponse)
def admin_list_conflicts(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """List films with potential duplicates."""
    films = (
        db.query(Film)
        .options(joinedload(Film.editions).joinedload(MovieEdition.media_files))
        .filter(Film.needs_review == True)  # noqa: E712
        .all()
    )

    items: list[dict] = []
    for film in films:
        editions = []
        for ed in film.editions:
            media_list = [
                ConflictMediaItem(
                    media_id=m.id, file_path=m.file_path,
                    file_size=m.file_size, codec=m.codec,
                    audio_codec=m.audio_codec, height=m.height,
                )
                for m in ed.media_files
            ]
            if not media_list:
                continue
            editions.append(ConflictEditionItem(
                edition_id=ed.id, quality=ed.quality,
                language=ed.language, media_files=media_list,
            ))
        if editions:
            items.append(ConflictItem(
                film_id=film.id, title=film.title,
                year=film.year, editions=editions,
            ))

    return {"items": items, "total": len(items)}


@router.patch("/conflicts/{film_id}/resolve", status_code=204)
def admin_resolve_conflict(
    film_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    """Mark a film as resolved (sets needs_review=False)."""
    film = db.get(Film, film_id)
    if film is None:
        raise HTTPException(status_code=404, detail="Film not found")
    film.needs_review = False
    db.commit()


@router.post("/conflicts/{film_id}/keep-edition/{edition_id}", status_code=200)
def admin_keep_edition(
    film_id: int,
    edition_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Keep only *edition_id* for *film_id*, removing all other editions' media files.

    Empty editions are deleted as a side effect.
    Sets ``needs_review = False``.
    Returns the number of deleted media files and editions.
    """
    film = db.get(Film, film_id)
    if film is None:
        raise HTTPException(status_code=404, detail="Film not found")

    deleted_media = 0
    deleted_editions = 0

    for ed in list(film.editions):
        if ed.id == edition_id:
            continue
        for mf in list(ed.media_files):
            db.delete(mf)
            deleted_media += 1
        db.delete(ed)
        deleted_editions += 1

    film.needs_review = False
    db.commit()
    return {
        "status": "ok",
        "film_id": film_id,
        "kept_edition_id": edition_id,
        "deleted_media": deleted_media,
        "deleted_editions": deleted_editions,
    }


@router.delete("/media/{media_id}", status_code=204)
def admin_delete_media(
    media_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> None:
    """Delete a specific MediaFile record (admin-only)."""
    media = db.get(MediaFile, media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="MediaFile not found")
    db.delete(media)
    db.commit()


# ---------------------------------------------------------------------------
# Transcoded files — list and manage .tr.mkv originals
# ---------------------------------------------------------------------------


@router.get("/transcoded-files")
def list_transcoded_files(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """List all transcoded (.tr) media files with their originals.

    Returns a list of entries, each containing the media file info,
    the original file path, whether the original still exists on disk,
    and the parent film title.
    """
    from pathlib import Path

    items: list[dict[str, object]] = []
    media_files = db.query(MediaFile).all()

    for mf in media_files:
        p = Path(mf.file_path)
        if ".tr" not in p.suffixes[:-1]:
            continue

        # Reconstruct original path: remove the .tr suffix component
        # e.g. "file.tr.mkv" → stem="file.tr" → original_stem="file"
        original_stem = p.stem[:-3] if p.stem.endswith(".tr") else p.stem
        original_path = p.parent / f"{original_stem}{p.suffix}"

        film = (
            db.query(Film.title)
            .join(MovieEdition, MovieEdition.film_id == Film.id)
            .filter(MovieEdition.id == mf.edition_id)
            .first()
        )

        items.append({
            "media_id": mf.id,
            "film_title": film[0] if film else "Unknown",
            "transcoded_path": mf.file_path,
            "original_path": str(original_path),
            "original_exists": original_path.is_file(),
        })

    return {"items": items, "total": len(items)}


@router.delete("/transcoded-files/original")
def delete_transcoded_original(
    original_path: str = Query(..., description="Absolute path to the original file"),
    current_user: User = Depends(require_role("admin")),
) -> dict[str, str]:
    """Delete the original (non-.tr) file from disk.

    This is an admin-only operation. The path must exist and must not
    contain ``.tr`` before the extension.
    """
    from pathlib import Path

    p = Path(original_path)
    if ".tr" in p.suffixes[:-1]:
        return {"status": "error", "error": "Refusing to delete a .tr file via this endpoint"}

    if not p.is_file():
        return {"status": "error", "error": f"File not found: {original_path}"}

    try:
        p.unlink()
        return {"status": "ok", "deleted": original_path}
    except OSError as exc:
        return {"status": "error", "error": str(exc)}


# ---------------------------------------------------------------------------
# Poster management
# ---------------------------------------------------------------------------

_poster_tasks: dict[str, dict[str, object]] = {}
_POSTER_TASK_ID = "poster-op"


@router.post("/posters/fill-missing", status_code=202)
def poster_fill_missing(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Fill missing posters for films that don't have one yet.

    Starts a background task. Poll ``GET /admin/jobs/{job_id}``
    for completion.
    """
    if not settings.omdb_api_key:
        return {
            "status": "error",
            "error": "OMDB_API_KEY is not configured. Set it in .env to use poster features.",
        }

    job = run_background_job(
        "poster_fill_missing", _run_fill_missing,
        session_factory=_background_session_factory,
    )
    return {"job_id": job.id, "status": "pending", "type": "poster_fill_missing"}


def _run_fill_missing(db: Session | None = None) -> dict | None:
    """Query films without posters and fill via OMDB."""
    close = db is None
    if db is None:
        db = SessionLocal()
    try:
        assert settings.omdb_api_key is not None
        api_key: str = settings.omdb_api_key

        films = db.query(Film).filter(Film.poster_url.is_(None)).all()
        updated = 0
        errors: list[str] = []

        for film in films:
            try:
                result = omdb_search_poster(film.title, film.year, api_key)
                if result is not None:
                    film.poster_url, film.poster_source = result
                    updated += 1
            except Exception as exc:
                errors.append(f"Film #{film.id} ({film.title}): {exc}")

        db.commit()
        return {"total": len(films), "updated": updated,
                "skipped": len(films) - updated, "errors": errors}
    except Exception:
        db.rollback()
        raise
    finally:
        if close:
            db.close()


@router.post("/posters/refresh-all", status_code=202)
def poster_refresh_all(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Refresh posters for all films, replacing existing ones.

    Starts a background task. Poll ``GET /admin/jobs/{job_id}``
    for completion.
    """
    if not settings.omdb_api_key:
        return {
            "status": "error",
            "error": "OMDB_API_KEY is not configured. Set it in .env to use poster features.",
        }

    job = run_background_job(
        "poster_refresh_all", _run_refresh_all,
        session_factory=_background_session_factory,
    )
    return {"job_id": job.id, "status": "pending", "type": "poster_refresh_all"}


def _run_refresh_all(db: Session | None = None) -> dict | None:
    """Refresh posters for all films via OMDB."""
    close = db is None
    if db is None:
        db = SessionLocal()
    try:
        assert settings.omdb_api_key is not None
        api_key: str = settings.omdb_api_key

        films = db.query(Film).all()
        updated = 0
        errors: list[str] = []

        for film in films:
            try:
                result = omdb_search_poster(film.title, film.year, api_key)
                if result is not None:
                    film.poster_url, film.poster_source = result
                    updated += 1
            except Exception as exc:
                errors.append(f"Film #{film.id} ({film.title}): {exc}")

        db.commit()
        return {"total": len(films), "updated": updated,
                "skipped": len(films) - updated, "errors": errors}
    except Exception:
        db.rollback()
        raise
    finally:
        if close:
            db.close()


# ---------------------------------------------------------------------------
# DeepSeek enrichment
# ---------------------------------------------------------------------------


@router.post("/enrich/deepseek", status_code=202)
def deepseek_enrich(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Enrich films that haven't been enriched by DeepSeek yet.

    Only processes films where ``metadata_source != "deepseek"``.
    Starts a background job. Poll ``GET /admin/jobs/{job_id}``
    for completion.
    """
    if not settings.deepseek_api_key:
        return {
            "status": "error",
            "error": (
                "DEEPSEEK_API_KEY is not configured."
                " Set it in .env to use DeepSeek enrichment."
            ),
        }

    job = run_background_job(
        "deepseek_enrich", _run_deepseek_enrich, False,
        session_factory=_background_session_factory,
    )
    return {"job_id": job.id, "status": "pending", "type": "deepseek_enrich"}


@router.post("/enrich/deepseek/all", status_code=202)
def deepseek_enrich_all(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Re-enrich ALL films via DeepSeek, overwriting existing data.

    Starts a background job. Poll ``GET /admin/jobs/{job_id}``
    for completion.
    """
    if not settings.deepseek_api_key:
        return {
            "status": "error",
            "error": (
                "DEEPSEEK_API_KEY is not configured."
                " Set it in .env to use DeepSeek enrichment."
            ),
        }

    job = run_background_job(
        "deepseek_enrich_all", _run_deepseek_enrich, True,
        session_factory=_background_session_factory,
    )
    return {"job_id": job.id, "status": "pending", "type": "deepseek_enrich_all"}


def _run_deepseek_enrich(force: bool, db: Session | None = None) -> dict | None:
    """Enrich films via DeepSeek.

    When *force* is ``False``, only films where ``metadata_source != "deepseek"``
    are processed.  When *force* is ``True``, all films are processed.
    """
    from filmoteka.domain.importing.pipeline import _apply_deepseek_enrichment
    from filmoteka.infrastructure.deepseek_provider import deepseek_enrich_metadata

    close = db is None
    if db is None:
        db = SessionLocal()
    try:
        assert settings.deepseek_api_key is not None
        api_key: str = settings.deepseek_api_key

        query = db.query(Film)
        if not force:
            query = query.filter(Film.metadata_source != "deepseek")

        films = query.all()
        updated = 0
        errors: list[str] = []

        for film in films:
            try:
                result = deepseek_enrich_metadata(film.title, film.year, api_key)
                if result is not None:
                    _apply_deepseek_enrichment(film, result, db)
                    updated += 1
            except Exception as exc:
                errors.append(f"Film #{film.id} ({film.title}): {exc}")

        db.commit()
        return {
            "total": len(films),
            "updated": updated,
            "skipped": len(films) - updated,
            "errors": errors,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if close:
            db.close()


# ---------------------------------------------------------------------------
# Media file aliases
# ---------------------------------------------------------------------------


@dataclass
class AliasFileStatus:
    media_id: int
    file_name: str
    status: str  # "queued" | "processing" | "completed" | "error"
    error: str | None = None


_alias_progress: dict[int, list[AliasFileStatus]] = {}
_active_alias_job_id: int | None = None
_alias_lock = threading.Lock()
_active_scan_job_id: int | None = None


@router.post("/alias/{media_id}/reset")
def reset_alias(
    media_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Reset a single media file's alias to its default (unprocessed) state.

    Sets ``media_alias = NULL`` and ``alias_processed = False`` so the
    file will be picked up by the next "Generate aliases (defaults only)"
    run.
    """
    mf = db.get(MediaFile, media_id)
    if mf is None:
        raise HTTPException(status_code=404, detail="MediaFile not found")
    mf.media_alias = None
    mf.alias_processed = False
    db.commit()
    return {"status": "ok", "media_id": media_id}


@router.get("/alias-progress/{job_id}")
def get_alias_progress(
    job_id: int,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Return per-file progress for an alias-generation job.

    Returns the list of ``AliasFileStatus`` entries — each entry
    has ``media_id``, ``file_name``, ``media_alias``, ``status``,
    and optionally ``error``.  The data lives in memory only and
    is cleared when a new alias job starts.
    """
    with _alias_lock:
        entries = _alias_progress.get(job_id)
        if entries is None:
            return {"entries": [], "total": 0}

        result_entries: list[dict[str, object]] = []
        for e in entries:
            media_alias: str | None = None
            if e.status == "completed":
                mf = db.get(MediaFile, e.media_id)
                if mf is not None:
                    media_alias = mf.media_alias
            result_entries.append({
                "media_id": e.media_id,
                "file_name": e.file_name,
                "media_alias": media_alias,
                "status": e.status,
                "error": e.error,
            })

        return {"entries": result_entries, "total": len(entries)}


@router.post("/aliases/generate", status_code=202)
def alias_generate(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Generate aliases for media files that haven't been processed yet.

    Only files where ``alias_processed`` is ``False`` are processed.
    Per-file progress is available at
    ``GET /admin/alias-progress/{job_id}`` for the duration of the job.

    Starts a background job. Poll ``GET /admin/jobs/{job_id}``
    for completion.
    """
    global _active_alias_job_id  # noqa: PLW0603

    if not settings.deepseek_api_key:
        return {
            "status": "error",
            "error": (
                "DEEPSEEK_API_KEY is not configured."
                " Set it in .env to use alias generation."
            ),
        }

    job = run_background_job(
        "alias_generate", _run_alias_generate, False,
        session_factory=_background_session_factory,
    )
    _active_alias_job_id = job.id
    with _alias_lock:
        _alias_progress.clear()
    return {"job_id": job.id, "status": "pending", "type": "alias_generate"}


@router.post("/aliases/generate-all", status_code=202)
def alias_generate_all(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Re-generate aliases for ALL media files, overwriting existing ones.

    Per-file progress is available at
    ``GET /admin/alias-progress/{job_id}`` for the duration of the job.

    Starts a background job. Poll ``GET /admin/jobs/{job_id}``
    for completion.
    """
    global _active_alias_job_id  # noqa: PLW0603

    if not settings.deepseek_api_key:
        return {
            "status": "error",
            "error": (
                "DEEPSEEK_API_KEY is not configured."
                " Set it in .env to use alias generation."
            ),
        }

    job = run_background_job(
        "alias_generate_all", _run_alias_generate, True,
        session_factory=_background_session_factory,
    )
    _active_alias_job_id = job.id
    with _alias_lock:
        _alias_progress.clear()
    return {"job_id": job.id, "status": "pending", "type": "alias_generate_all"}


def _run_alias_generate(force: bool, db: Session | None = None) -> dict | None:
    """Generate media aliases via DeepSeek.

    When *force* is ``False``, only files where ``alias_processed`` is
    ``False`` are processed.  When *force* is ``True``, all media files
    are processed regardless.

    Progress is written to the in-memory ``_alias_progress`` dict,
    keyed by the active job id.
    """
    from pathlib import Path

    from filmoteka.infrastructure.deepseek_provider import deepseek_generate_alias

    close = db is None
    if db is None:
        db = SessionLocal()
    try:
        assert settings.deepseek_api_key is not None
        api_key: str = settings.deepseek_api_key

        query = db.query(MediaFile)
        if not force:
            query = query.filter(MediaFile.alias_processed == sa_false())

        media_files = query.all()
        updated = 0
        errors: list[str] = []

        # Initialise in-memory progress table (all queued).
        progress: list[AliasFileStatus] = [
            AliasFileStatus(
                media_id=mf.id,
                file_name=Path(mf.file_path).name,
                status="queued",
            )
            for mf in media_files
        ]
        job_id = _active_alias_job_id or 0
        with _alias_lock:
            _alias_progress[job_id] = progress

        for idx, mf in enumerate(media_files):
            # ── Check for cancellation ──
            if should_stop(job_id, _background_session_factory):
                _logger.info("Alias job %d cancelled — stopping", job_id)
                break

            with _alias_lock:
                progress[idx].status = "processing"

            try:
                file_stem = Path(mf.file_path).stem
                alias = deepseek_generate_alias(file_stem, api_key)
                if alias is not None:
                    mf.media_alias = alias
                    mf.alias_processed = True
                    updated += 1
                    with _alias_lock:
                        progress[idx].status = "completed"
                else:
                    # LLM returned nothing — don't mark as processed
                    # so "defaults only" retries the file next time.
                    errors.append(
                        f"MediaFile #{mf.id} ({mf.file_path}):"
                        f" LLM returned no alias"
                    )
                    with _alias_lock:
                        progress[idx].status = "error"
                        progress[idx].error = "LLM returned no alias"
            except Exception as exc:
                errors.append(f"MediaFile #{mf.id} ({mf.file_path}): {exc}")
                # Ensure a default alias exists
                if mf.media_alias is None:
                    mf.media_alias = Path(mf.file_path).stem
                # Keep alias_processed = False so "defaults only" retries
                with _alias_lock:
                    progress[idx].status = "error"
                    progress[idx].error = str(exc)

        db.commit()
        return {
            "total": len(media_files),
            "updated": updated,
            "skipped": len(media_files) - updated,
            "errors": errors,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if close:
            db.close()


# ---------------------------------------------------------------------------
# Film card editing
# ---------------------------------------------------------------------------


@router.put("/films/{film_id}")
def update_film(
    film_id: int,
    body: FilmUpdateSchema,
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> FilmDetailOut:
    """Update a film card. Only provided fields are changed.

    Admin-only. Resets ``needs_review`` and sets metadata source to ``manual``
    to reflect human verification.
    """
    film = (
        db.query(Film)
        .options(
            joinedload(Film.genres),
            joinedload(Film.editions).joinedload(MovieEdition.media_files),
        )
        .filter(Film.id == film_id)
        .one_or_none()
    )
    if film is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Film not found",
        )

    changed = False
    if body.title is not None and body.title != film.title:
        film.title = body.title
        changed = True
    if body.year is not None and body.year != film.year:
        film.year = body.year
        changed = True
    if body.description is not None and body.description != film.description:
        film.description = body.description
        changed = True
    if body.age_rating is not None and body.age_rating != film.age_rating:
        film.age_rating = body.age_rating
        changed = True
    if body.is_family_video is not None and body.is_family_video != film.is_family_video:
        film.is_family_video = body.is_family_video
        changed = True
    if body.poster_url is not None and body.poster_url != film.poster_url:
        film.poster_url = body.poster_url
        film.poster_source = "manual"
        changed = True
    if body.country is not None and body.country != film.country:
        film.country = body.country
        changed = True

    if changed:
        film.needs_review = False
        film.metadata_source = "manual"
        film.metadata_confidence = 1.0
        film.metadata_enriched_at = datetime.now()

    db.commit()
    db.refresh(film)

    # Reload relations after commit
    rows = (
        db.execute(
            select(film_person.c.role, Person).join(
                Person, film_person.c.person_id == Person.id
            ).where(film_person.c.film_id == film_id)
        )
        .all()
    )
    persons = [
        PersonOut(id=row.Person.id, name=row.Person.name, role=row.role)
        for row in rows
    ]

    return FilmDetailOut(
        id=film.id,
        title=film.title,
        year=film.year,
        description=film.description,
        poster_url=film.poster_url,
        age_rating=film.age_rating,
        is_family_video=film.is_family_video,
        country=film.country,
        needs_review=film.needs_review,
        created_at=film.created_at,
        genres=[GenreOut.model_validate(g) for g in film.genres],
        persons=persons,
        editions=[
            EditionOut(
                id=e.id,
                edition_name=e.edition_name,
                quality=e.quality,
                language=e.language,
                media_files=[MediaFileOut.model_validate(m) for m in e.media_files],
            )
            for e in film.editions
        ],
    )


# ---------------------------------------------------------------------------
# Media re-index
# ---------------------------------------------------------------------------


@router.post("/media/reindex", status_code=202)
def media_reindex(
    current_user: User = Depends(require_role("admin")),
    config: LibraryConfig = Depends(get_library_config),
) -> dict[str, object]:
    """Re-index media files whose stored paths no longer resolve on disk.

    Scans all ``MediaFile`` records, checks whether ``file_path`` exists,
    and if not, searches for the file by name under the configured library
    root (``target_root``).  Matching records are updated in-place.

    Starts a background task. Poll ``GET /admin/jobs/{job_id}``
    for completion.
    """
    job = run_background_job(
        "media_reindex", _run_reindex, config,
        session_factory=_background_session_factory,
    )
    return {"job_id": job.id, "status": "pending", "type": "media_reindex"}


def _run_reindex(config: LibraryConfig, db: Session | None = None) -> dict | None:
    """Re-index media file paths."""
    close = db is None
    if db is None:
        db = SessionLocal()
    try:
        lib_root = config.paths.target_root
        media_files = db.query(MediaFile).all()

        fixed = 0
        not_found = 0
        skipped = 0

        for mf in media_files:
            stored = Path(mf.file_path)
            if stored.is_file():
                skipped += 1
                continue

            resolved = _reindex_resolve_path(mf.file_path, lib_root)
            if resolved is not None:
                _logger.info(
                    "Re-indexed media %d: %s → %s", mf.id, mf.file_path, resolved
                )
                mf.file_path = str(resolved)
                fixed += 1
            else:
                not_found += 1

        db.commit()
        return {
            "total": len(media_files), "fixed": fixed,
            "not_found": not_found, "skipped": skipped,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if close:
            db.close()


def _reindex_resolve_path(stored_path: str, library_root: Path) -> Path | None:
    """Resolve a stored media path under *library_root*.

    Looks for a file with the same basename recursively.  If multiple
    matches exist, tries to disambiguate by matching the last 2 path
    components (parent-dir + filename).
    """
    name = Path(stored_path).name
    if not name or not library_root.is_dir():
        return None

    matches = list(library_root.rglob(name))
    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        stored = Path(stored_path)
        tail_parts = stored.parts[-2:] if len(stored.parts) >= 2 else stored.parts
        tail = "/".join(tail_parts)
        for m in matches:
            try:
                if str(m.relative_to(library_root)) == tail:
                    return m
            except ValueError:
                continue

    return None


# ---------------------------------------------------------------------------
# Media reconcile — reindex + cleanup orphaned records
# ---------------------------------------------------------------------------


@router.post("/media/reconcile", status_code=202)
def media_reconcile(
    current_user: User = Depends(require_role("admin")),
    config: LibraryConfig = Depends(get_library_config),
) -> dict[str, object]:
    """Reconcile the media library with the filesystem.

    Performs three steps in a single background job:

    1. **Reindex** — fix ``MediaFile.file_path`` for files that exist on
       disk under a different path.
    2. **Cleanup** — delete ``MediaFile`` records whose underlying file
       could not be found anywhere under the library root.
    3. **Cascade** — delete ``MovieEdition`` records that no longer have
       any ``MediaFile`` children, and mark ``Film`` records that have
       lost all their editions as ``needs_review``.

    Poll ``GET /admin/jobs/{job_id}`` for completion.
    """
    job = run_background_job(
        "media_reconcile", _run_reconcile, config,
        session_factory=_background_session_factory,
    )
    return {"job_id": job.id, "status": "pending", "type": "media_reconcile"}


def _run_reconcile(config: LibraryConfig, db: Session | None = None) -> dict | None:
    """Reindex + cleanup orphaned catalog records."""
    close = db is None
    if db is None:
        db = SessionLocal()
    try:
        lib_root = config.paths.target_root
        media_files = db.query(MediaFile).all()

        reindexed = 0
        deleted_media = 0
        errors: list[str] = []

        # ── Step 1 & 2: reindex or delete each MediaFile ──
        for mf in media_files:
            stored = Path(mf.file_path)
            if stored.is_file():
                continue

            resolved = _reindex_resolve_path(mf.file_path, lib_root)
            if resolved is not None:
                _logger.info(
                    "Re-indexed media %d: %s → %s", mf.id, mf.file_path, resolved,
                )
                mf.file_path = str(resolved)
                reindexed += 1
            else:
                _logger.info(
                    "Removing orphaned MediaFile %d (%s)", mf.id, mf.file_path,
                )
                db.delete(mf)
                deleted_media += 1

        db.flush()

        # ── Step 3: cascade cleanup ──
        from sqlalchemy import func as sa_func

        # Find MovieEdition records with zero MediaFiles
        empty_editions = (
            db.query(MovieEdition)
            .outerjoin(MediaFile, MediaFile.edition_id == MovieEdition.id)
            .group_by(MovieEdition.id)
            .having(sa_func.count(MediaFile.id) == 0)
            .all()
        )
        deleted_editions = len(empty_editions)
        for ed in empty_editions:
            _logger.info("Removing empty MovieEdition %d", ed.id)
            db.delete(ed)

        db.flush()

        # Find Film records with zero editions
        empty_films = (
            db.query(Film)
            .outerjoin(MovieEdition, MovieEdition.film_id == Film.id)
            .group_by(Film.id)
            .having(sa_func.count(MovieEdition.id) == 0)
            .all()
        )
        flagged_films = len(empty_films)
        for film in empty_films:
            _logger.info("Flagging empty Film %d (%s) as needs_review", film.id, film.title)
            film.needs_review = True

        db.commit()
        return {
            "total": len(media_files),
            "reindexed": reindexed,
            "deleted_media": deleted_media,
            "deleted_editions": deleted_editions,
            "flagged_films": flagged_films,
            "errors": errors,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if close:
            db.close()


# ---------------------------------------------------------------------------
# In-memory per-file progress for audio transcoding (session-only)
# ---------------------------------------------------------------------------


@dataclass
class TranscodeFileStatus:
    media_id: int
    file_name: str
    status: str  # "queued" | "probing" | "transcoding" | "completed" | "skipped" | "error"
    error: str | None = None


# Global state for the current transcode job, keyed by job_id.
# Only one transcode job runs at a time.  Cleared when a new job starts.
_transcode_progress: dict[int, list[TranscodeFileStatus]] = {}
_active_transcode_job_id: int | None = None
_transcode_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Audio transcoding (AC3/E-AC3 → AAC)
# ---------------------------------------------------------------------------


@router.get("/transcode-progress/{job_id}")
def get_transcode_progress(
    job_id: int,
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Return per-file progress for a transcode audio job.

    Returns the list of ``TranscodeFileStatus`` entries — each entry
    has ``media_id``, ``file_name``, ``status``, and optionally
    ``error``.  The data lives in memory only and is cleared when a
    new transcode job starts.
    """
    with _transcode_lock:
        entries = _transcode_progress.get(job_id)
        if entries is None:
            return {"entries": [], "total": 0}
        return {
            "entries": [
                {
                    "media_id": e.media_id,
                    "file_name": e.file_name,
                    "status": e.status,
                    "error": e.error,
                }
                for e in entries
            ],
            "total": len(entries),
        }


@router.post("/media/transcode-audio", status_code=202)
def transcode_media_audio(
    current_user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Transcode AC3/E-AC3 audio tracks to AAC for all media files.

    Files with AC3/E-AC3 audio are probed via ffprobe then transcoded
    in-place using ffmpeg (video copy, audio only).  After transcoding
    the browser can render a proper seekable progress bar.

    Per-file progress is available at
    ``GET /admin/transcode-progress/{job_id}`` for the duration of the
    job.

    Starts a background task.  Poll ``GET /admin/jobs/{job_id}``
    for completion.
    """
    global _active_transcode_job_id  # noqa: PLW0603

    # Guard against concurrent transcodes
    if _active_transcode_job_id is not None:
        existing = db.get(BackgroundJob, _active_transcode_job_id)
        if existing is not None and existing.status == "running":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A transcode job is already in progress",
            )

    job = run_background_job(
        "transcode_audio", _run_transcode_audio,
        session_factory=_background_session_factory,
    )
    _active_transcode_job_id = job.id
    with _transcode_lock:
        _transcode_progress.clear()
    return {"job_id": job.id, "status": "pending", "type": "transcode_audio"}


def _clean_orphan_ac3fix(db: Session) -> None:
    """Remove stale ``.ac3fix.mkv`` temporary files and their DB records.

    These are left behind when :func:`_run_transcode_audio` is
    interrupted (API restart) before the ffmpeg temp file could be
    renamed to ``.tr.mkv``.
    """
    orphans = (
        db.query(MediaFile)
        .filter(MediaFile.file_path.like("%.ac3fix%"))
        .all()
    )
    if not orphans:
        return
    _logger.info("Cleaning %d orphan .ac3fix file(s)", len(orphans))
    for mf in orphans:
        p = Path(mf.file_path)
        if p.is_file():
            p.unlink(missing_ok=True)
            _logger.debug("Deleted orphan file: %s", p.name)
        db.delete(mf)
    db.commit()


def _run_transcode_audio(db: Session | None = None) -> dict | None:
    """Scan all media files, probe for AC3/E-AC3, transcode to AAC."""
    close = db is None
    if db is None:
        db = SessionLocal()
    try:
        # Clean up orphan .ac3fix.mkv files from previous failed sessions
        _clean_orphan_ac3fix(db)

        media_files = db.query(MediaFile).all()
        total = len(media_files)
        transcoded = 0
        skipped = 0
        errors: list[str] = []
        consecutive_timeouts = 0

        # Initialise in-memory progress table (all queued).
        progress: list[TranscodeFileStatus] = [
            TranscodeFileStatus(
                media_id=mf.id,
                file_name=Path(mf.file_path).name,
                status="queued",
            )
            for mf in media_files
        ]
        job_id = _active_transcode_job_id or 0
        with _transcode_lock:
            _transcode_progress[job_id] = progress

        for idx, mf in enumerate(media_files):
            path = Path(mf.file_path)

            # ── Check for cancellation ──
            if should_stop(job_id, _background_session_factory):
                _logger.info("Transcode job %d cancelled — stopping", job_id)
                break

            # ── Probe ──
            with _transcode_lock:
                progress[idx].status = "probing"
            if not path.is_file():
                with _transcode_lock:
                    progress[idx].status = "skipped"
                skipped += 1
                continue

            try:
                probe = probe_media(path)
            except MediaProbeError:
                with _transcode_lock:
                    progress[idx].status = "skipped"
                skipped += 1
                continue

            codec_raw = (probe.audio_codec or "").lower()
            if codec_raw not in ("ac3", "eac3"):
                with _transcode_lock:
                    progress[idx].status = "skipped"
                skipped += 1
                continue

            # ── Transcode ──
            with _transcode_lock:
                progress[idx].status = "transcoding"

            # NOTE: keep .mkv extension so ffmpeg can detect the muxer format.
            temp_path = path.parent / f".{path.stem}.ac3fix{path.suffix}"
            try:
                cmd = [
                    "ffmpeg",
                    "-i", str(path),
                    "-c:v", "copy",
                    "-c:a", "aac",
                    "-b:a", "256k",
                    "-y",
                    str(temp_path),
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    errors="replace", timeout=7200,
                )
                if result.returncode != 0:
                    msg = result.stderr.strip()[:500] or "(no stderr)"
                    _logger.warning(
                        "ffmpeg failed for media %d (%s) exit %d: %s",
                        mf.id, path.name, result.returncode,
                        result.stderr.strip()[-500:],
                    )
                    errors.append(
                        f"Media {mf.id} ({path.name}): ffmpeg error — {msg}",
                    )
                    temp_path.unlink(missing_ok=True)
                    with _transcode_lock:
                        progress[idx].status = "error"
                        progress[idx].error = msg
                    continue

                # Place transcoded file alongside original with .tr suffix
                result_path = path.parent / f"{path.stem}.tr{path.suffix}"
                temp_path.rename(result_path)
                mf.file_path = str(result_path)
                mf.audio_codec = "aac"
                db.commit()
                _logger.info(
                    "Transcoded AC3→AAC for media %d: %s", mf.id, result_path.name,
                )
                transcoded += 1
                consecutive_timeouts = 0
                with _transcode_lock:
                    progress[idx].status = "completed"
            except subprocess.TimeoutExpired:
                errors.append(f"Media {mf.id} ({path.name}): ffmpeg timed out")
                temp_path.unlink(missing_ok=True)
                with _transcode_lock:
                    progress[idx].status = "error"
                    progress[idx].error = "ffmpeg timed out"
                consecutive_timeouts += 1
                if consecutive_timeouts >= 3:
                    _logger.warning(
                        "Transcode job %d aborted — %d consecutive timeouts",
                        job_id, consecutive_timeouts,
                    )
                    break
            except Exception as exc:
                errors.append(f"Media {mf.id} ({path.name}): {exc}")
                temp_path.unlink(missing_ok=True)
                with _transcode_lock:
                    progress[idx].status = "error"
                    progress[idx].error = str(exc)

        db.commit()
        aborted = consecutive_timeouts >= 3
        if aborted:
            raise RuntimeError(
                f"Stopped after {consecutive_timeouts} consecutive timeouts"
            )
        return {
            "total": total,
            "transcoded": transcoded,
            "skipped": skipped,
            "error_count": len(errors),
            "errors": errors,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if close:
            db.close()
