"""Catalog endpoints: film listing and card."""

# ruff: noqa: B008  FastAPI requires Depends() in function signatures

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import false as sa_false
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from filmoteka.api.auth import get_optional_current_user
from filmoteka.api.schemas.catalog import (
    EditionOut,
    FilmDetailOut,
    FilmListResponse,
    FilmOut,
    GenreOut,
    MediaFileOut,
    PersonOut,
)
from filmoteka.domain.access.models import User, UserFilmBlacklist
from filmoteka.domain.catalog.models import (
    Film,
    Genre,
    MediaFile,
    MovieEdition,
    Person,
    film_person,
)
from filmoteka.domain.watching.models import WatchEvent
from filmoteka.infrastructure.database import get_db

router = APIRouter(prefix="/films", tags=["catalog"])


_RESOLUTION_MAP: dict[str, int] = {
    "4k": 2160,
    "2160": 2160,
    "2160p": 2160,
    "uhd": 2160,
    "1440": 1440,
    "1440p": 1440,
    "2k": 1440,
    "1080": 1080,
    "1080p": 1080,
    "hd": 1080,
    "720": 720,
    "720p": 720,
    "sd": 480,
    "480": 480,
    "480p": 480,
}


def _min_height(resolution: str) -> int | None:
    """Return the minimum pixel height for a resolution label, or ``None``
    if unrecognised."""
    return _RESOLUTION_MAP.get(resolution.strip().lower())


_AGE_GROUP_MAX: dict[str, int] = {
    "0_6": 6,
    "7_12": 12,
    "13_17": 16,
}

_AGE_RATING_VALUES: dict[str, int] = {
    "0+": 0,
    "6+": 6,
    "12+": 12,
    "16+": 16,
    "18+": 18,
}


@router.get("", response_model=FilmListResponse)
def list_films(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    year: int | None = Query(None),
    year_from: int | None = Query(None),
    year_to: int | None = Query(None),
    genre: str | None = Query(None, min_length=1),
    q: str | None = Query(None, min_length=1),
    resolution: str | None = Query(None, min_length=1),
    codec: str | None = Query(None, min_length=1),
    audio_codec: str | None = Query(None, min_length=1),
    has_subtitles: bool | None = Query(None),
    audio_lang: str | None = Query(None, min_length=1),
    subtitle_lang: str | None = Query(None, min_length=1),
    include_family: bool = Query(False),
    current_user: User | None = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> FilmListResponse:
    """Return a paginated list of films, optionally filtered by year range,
    genre slug, exact year, free-text search, or tech attributes (resolution,
    video codec, audio codec, subtitle presence, audio/subtitle language).

    Tech attributes are matched against ``MediaFile`` records reachable
    through ``Film → MovieEdition → MediaFile``.
    """
    query = db.query(Film)

    if q:
        query = query.filter(
            Film.title.ilike(f"%{q}%")
            | Film.description.ilike(f"%{q}%")
            | Film.genres.any(Genre.name.ilike(f"%{q}%"))
            | Film.persons.any(Person.name.ilike(f"%{q}%"))
            | Film.id.in_(
                db.query(MovieEdition.film_id)
                .join(MediaFile)
                .filter(MediaFile.media_alias.ilike(f"%{q}%"))
            )
        )

    if genre is not None:
        query = query.filter(Film.genres.any(Genre.slug == genre))

    if year is not None:
        query = query.filter(Film.year == year)
    else:
        if year_from is not None:
            query = query.filter(Film.year >= year_from)
        if year_to is not None:
            query = query.filter(Film.year <= year_to)

    # ── Tech attribute filters (via Film → MovieEdition → MediaFile) ──

    if resolution is not None:
        min_h = _min_height(resolution)
        if min_h is not None:
            query = query.filter(
                Film.id.in_(
                    db.query(MovieEdition.film_id)
                    .join(MediaFile)
                    .filter(MediaFile.height >= min_h)
                )
            )

    if codec is not None:
        query = query.filter(
            Film.id.in_(
                db.query(MovieEdition.film_id)
                .join(MediaFile)
                .filter(MediaFile.codec.ilike(f"%{codec}%"))
            )
        )

    if audio_codec is not None:
        query = query.filter(
            Film.id.in_(
                db.query(MovieEdition.film_id)
                .join(MediaFile)
                .filter(MediaFile.audio_codec.ilike(f"%{audio_codec}%"))
            )
        )

    if has_subtitles is True:
        query = query.filter(
            Film.id.in_(
                db.query(MovieEdition.film_id)
                .join(MediaFile)
                .filter(MediaFile.subtitle_languages.isnot(None))
            )
        )

    if audio_lang is not None:
        query = query.filter(
            Film.id.in_(
                db.query(MovieEdition.film_id)
                .join(MediaFile)
                .filter(MediaFile.audio_codec.ilike(f"%{audio_lang}%"))
            )
        )

    if subtitle_lang is not None:
        query = query.filter(
            Film.id.in_(
                db.query(MovieEdition.film_id)
                .join(MediaFile)
                .filter(MediaFile.subtitle_languages.ilike(f"%{subtitle_lang}%"))
            )
        )

    # ── Child-restriction: age-rating filter ──────────────────────

    is_child = (
        current_user is not None
        and current_user.role == "child"
        and current_user.age_group is not None
    )
    if is_child:
        max_age = _AGE_GROUP_MAX.get(current_user.age_group)  # type: ignore[union-attr]
        if max_age is not None:
            allowed_ratings = [
                r for r, v in _AGE_RATING_VALUES.items() if v <= max_age
            ]
            query = query.filter(
                or_(
                    Film.age_rating.is_(None),
                    Film.age_rating.in_(allowed_ratings),
                )
            )

    # ── Blacklist: exclude films the user has blacklisted ────────

    if current_user is not None:
        blacklisted_ids = (
            db.query(UserFilmBlacklist.film_id)
            .filter(UserFilmBlacklist.user_id == current_user.id)
            .scalar_subquery()
        )
        query = query.filter(Film.id.notin_(blacklisted_ids))

    # ── Family video: exclude by default ─────────────────────────

    if not include_family:
        query = query.filter(Film.is_family_video == False)  # noqa: E712

    # ── Exclude watched: hide films the user has started ─────────

    if current_user is not None and current_user.exclude_watched:
        watched_ids = (
            db.query(MovieEdition.film_id)
            .join(MediaFile)
            .join(WatchEvent)
            .filter(
                WatchEvent.user_id == current_user.id,
                WatchEvent.incognito == sa_false(),
            )
            .distinct()
            .subquery()
        )
        query = query.filter(Film.id.notin_(watched_ids))

    total = query.count()
    items = query.order_by(Film.created_at.desc()).offset(skip).limit(limit).all()

    return FilmListResponse(
        items=[FilmOut.model_validate(f) for f in items],
        total=total,
    )


@router.get("/{film_id}", response_model=FilmDetailOut)
def get_film(
    film_id: int,
    db: Session = Depends(get_db),
) -> FilmDetailOut:
    """Return detailed film card with genres, persons, editions, and media files."""
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

    # Persons with roles from the association table.
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
