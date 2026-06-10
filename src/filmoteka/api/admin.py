"""Admin-only endpoints."""

# ruff: noqa: B008  FastAPI requires Depends() in function signatures

from __future__ import annotations

import logging
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
from filmoteka.domain.tasks.models import BackgroundJob
from filmoteka.domain.tasks.worker import run_background_job
from filmoteka.domain.watching.models import WatchEvent
from filmoteka.infrastructure.database import SessionLocal, get_db
from filmoteka.infrastructure.library_config import LibraryConfig
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
            continue

    return {"items": suggestions[:30], "total": len(suggestions[:30])}


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
) -> dict[str, object]:
    """Start a background library scan.

    Returns immediately with 202 and a ``job_id``. Poll
    ``GET /admin/jobs/{job_id}`` for completion.
    """
    job = run_background_job(
        "import_scan", _run_import_job, config,
        session_factory=_background_session_factory,
    )
    return {"job_id": job.id, "status": "pending", "type": "import_scan"}


def _run_import_job(config: LibraryConfig) -> dict | None:
    """Run import pipeline and return the import report dict."""
    db = SessionLocal()
    try:
        report = run_import(config, db)
        return report.to_dict()
    finally:
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
