"""Catalog endpoints: film listing."""

# ruff: noqa: B008  FastAPI requires Depends() in function signatures

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from filmoteka.api.schemas.catalog import FilmListResponse, FilmOut
from filmoteka.domain.catalog.models import Film
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
