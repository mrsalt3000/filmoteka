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
    MovieEdition,
    Person,
    film_person,
)
from filmoteka.infrastructure.database import get_db

router = APIRouter(prefix="/films", tags=["catalog"])


@router.get("", response_model=FilmListResponse)
def list_films(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    year: int | None = Query(None),
    db: Session = Depends(get_db),
) -> FilmListResponse:
    """Return a paginated list of films, optionally filtered by year."""
    query = db.query(Film)

    if year is not None:
        query = query.filter(Film.year == year)

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
