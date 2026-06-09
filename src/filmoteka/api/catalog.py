"""Catalog endpoints: film listing and card."""

# ruff: noqa: B008  FastAPI requires Depends() in function signatures

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from filmoteka.api.schemas.catalog import (
    EditionOut,
    FilmDetailOut,
    FilmListResponse,
    FilmOut,
    GenreOut,
    MediaFileOut,
    PersonOut,
)
from filmoteka.domain.catalog.models import (
    Film,
    Genre,
    MediaFile,
    MovieEdition,
    Person,
    film_person,
)
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
    db: Session = Depends(get_db),
) -> FilmListResponse:
    """Return a paginated list of films, optionally filtered by year range,
    genre slug, exact year, free-text search, or tech attributes (resolution,
    video codec, audio codec, subtitle presence).

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
