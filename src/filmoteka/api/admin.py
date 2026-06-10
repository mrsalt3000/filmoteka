"""Admin-only endpoints."""

# ruff: noqa: B008  FastAPI requires Depends() in function signatures

from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
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
    EditionOut,
    FilmDetailOut,
    FilmUpdateSchema,
    GenreOut,
    MediaFileOut,
    PersonOut,
)
from filmoteka.domain.access.models import User
from filmoteka.domain.access.service import hash_password
from filmoteka.domain.catalog.models import (
    Film,
    MediaFile,
    MovieEdition,
    Person,
    film_person,
)
from filmoteka.domain.importing.pipeline import run_import
from filmoteka.infrastructure.database import SessionLocal, get_db
from filmoteka.infrastructure.library_config import LibraryConfig
from filmoteka.infrastructure.metadata_providers import omdb_search_poster
from filmoteka.infrastructure.settings import settings

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# In-memory store: { task_id: { "status": str, "report": dict|None, "error": str|None } }
_import_tasks: dict[str, dict[str, object]] = {}
_TASK_ID = "import-scan"  # single-slot for simplicity


@router.get("/health")
def admin_health(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, str]:
    """Simple admin-only health check."""
    return {"status": "ok", "role": current_user.role, "username": current_user.username}


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

    Returns immediately with 202. Poll ``GET /admin/import/status``
    for completion.
    """
    task = _import_tasks.get(_TASK_ID)
    if task and task["status"] == "running":
        return {"task_id": _TASK_ID, "status": "running", "message": "Scan already in progress"}

    _import_tasks[_TASK_ID] = {"status": "running", "report": None, "error": None}

    def _run() -> None:
        db = SessionLocal()
        try:
            report = run_import(config, db)
            _import_tasks[_TASK_ID] = {
                "status": "completed",
                "report": report.to_dict(),
                "error": None,
            }
        except Exception as exc:
            _import_tasks[_TASK_ID] = {
                "status": "failed",
                "report": None,
                "error": str(exc),
            }
        finally:
            db.close()

    threading.Thread(target=_run, daemon=True).start()

    return {"task_id": _TASK_ID, "status": "running", "message": "Scan started"}


@router.get("/import/status")
def import_status(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Return the status of the last library scan."""
    task = _import_tasks.get(_TASK_ID)
    if task is None:
        return {"task_id": _TASK_ID, "status": "idle", "report": None, "error": None}
    return {"task_id": _TASK_ID, **task}


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

    Starts a background task. Poll ``GET /admin/posters/status``
    for completion.
    """
    if not settings.omdb_api_key:
        return {
            "task_id": _POSTER_TASK_ID,
            "status": "error",
            "error": "OMDB_API_KEY is not configured. Set it in .env to use poster features.",
        }

    task = _poster_tasks.get(_POSTER_TASK_ID)
    if task and task["status"] == "running":
        return {
            "task_id": _POSTER_TASK_ID,
            "status": "running",
            "message": "Poster operation already in progress",
        }

    _poster_tasks[_POSTER_TASK_ID] = {"status": "running", "report": None, "error": None}

    def _run() -> None:
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

            _poster_tasks[_POSTER_TASK_ID] = {
                "status": "completed",
                "report": {
                    "total": len(films),
                    "updated": updated,
                    "skipped": len(films) - updated,
                    "errors": errors,
                },
                "error": None,
            }
        except Exception as exc:
            db.rollback()
            _poster_tasks[_POSTER_TASK_ID] = {
                "status": "failed",
                "report": None,
                "error": str(exc),
            }
        finally:
            db.close()

    threading.Thread(target=_run, daemon=True).start()

    msg = "Fill missing posters started"
    return {"task_id": _POSTER_TASK_ID, "status": "running", "message": msg}


@router.post("/posters/refresh-all", status_code=202)
def poster_refresh_all(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Refresh posters for all films, replacing existing ones.

    Starts a background task. Poll ``GET /admin/posters/status``
    for completion.
    """
    if not settings.omdb_api_key:
        return {
            "task_id": _POSTER_TASK_ID,
            "status": "error",
            "error": "OMDB_API_KEY is not configured. Set it in .env to use poster features.",
        }

    task = _poster_tasks.get(_POSTER_TASK_ID)
    if task and task["status"] == "running":
        return {
            "task_id": _POSTER_TASK_ID,
            "status": "running",
            "message": "Poster operation already in progress",
        }

    _poster_tasks[_POSTER_TASK_ID] = {"status": "running", "report": None, "error": None}

    def _run() -> None:
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

            _poster_tasks[_POSTER_TASK_ID] = {
                "status": "completed",
                "report": {
                    "total": len(films),
                    "updated": updated,
                    "skipped": len(films) - updated,
                    "errors": errors,
                },
                "error": None,
            }
        except Exception as exc:
            db.rollback()
            _poster_tasks[_POSTER_TASK_ID] = {
                "status": "failed",
                "report": None,
                "error": str(exc),
            }
        finally:
            db.close()

    threading.Thread(target=_run, daemon=True).start()

    msg = "Refresh all posters started"
    return {"task_id": _POSTER_TASK_ID, "status": "running", "message": msg}


@router.get("/posters/status")
def poster_status(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Return the status of the last poster operation."""
    task = _poster_tasks.get(_POSTER_TASK_ID)
    if task is None:
        return {"task_id": _POSTER_TASK_ID, "status": "idle", "report": None, "error": None}
    return {"task_id": _POSTER_TASK_ID, **task}


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

_reindex_tasks: dict[str, dict[str, object]] = {}
_REINDEX_TASK_ID = "media-reindex"


@router.post("/media/reindex", status_code=202)
def media_reindex(
    current_user: User = Depends(require_role("admin")),
    config: LibraryConfig = Depends(get_library_config),
) -> dict[str, object]:
    """Re-index media files whose stored paths no longer resolve on disk.

    Scans all ``MediaFile`` records, checks whether ``file_path`` exists,
    and if not, searches for the file by name under the configured library
    root (``target_root``).  Matching records are updated in-place.

    Starts a background task. Poll ``GET /admin/media/reindex/status``
    for completion.
    """
    task = _reindex_tasks.get(_REINDEX_TASK_ID)
    if task and task["status"] == "running":
        return {
            "task_id": _REINDEX_TASK_ID,
            "status": "running",
            "message": "Re-index already in progress",
        }

    _reindex_tasks[_REINDEX_TASK_ID] = {"status": "running", "report": None, "error": None}

    def _run() -> None:
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

                # Try to locate the file under the library root
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

            _reindex_tasks[_REINDEX_TASK_ID] = {
                "status": "completed",
                "report": {
                    "total": len(media_files),
                    "fixed": fixed,
                    "not_found": not_found,
                    "skipped": skipped,
                },
                "error": None,
            }
        except Exception as exc:
            db.rollback()
            _logger.exception("Media re-index failed")
            _reindex_tasks[_REINDEX_TASK_ID] = {
                "status": "failed",
                "report": None,
                "error": str(exc),
            }
        finally:
            db.close()

    threading.Thread(target=_run, daemon=True).start()

    return {"task_id": _REINDEX_TASK_ID, "status": "running", "message": "Media re-index started"}


@router.get("/media/reindex/status")
def media_reindex_status(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Return the status of the last media re-index operation."""
    task = _reindex_tasks.get(_REINDEX_TASK_ID)
    if task is None:
        return {"task_id": _REINDEX_TASK_ID, "status": "idle", "report": None, "error": None}
    return {"task_id": _REINDEX_TASK_ID, **task}


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
