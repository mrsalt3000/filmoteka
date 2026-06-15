# ruff: noqa: B008  FastAPI requires Depends() in function signatures

"""Series API endpoints — list, detail, and episode browsing."""

from __future__ import annotations

import logging
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from filmoteka.api.schemas.catalog import (
    EpisodeOut,
    SeasonGroup,
    SeriesDetailOut,
    SeriesEpisodesResponse,
    SeriesListItem,
    SeriesListResponse,
)
from filmoteka.domain.catalog.models import Film, MovieEdition, Series
from filmoteka.infrastructure.database import get_db

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/series", tags=["series"])


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("", response_model=SeriesListResponse)
def list_series(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> SeriesListResponse:
    """Return a paginated list of all series with episode counts."""
    # Subquery: count films per series
    ep_count = (
        db.query(Film.series_id, func.count(Film.id).label("cnt"))
        .filter(Film.series_id.isnot(None))
        .group_by(Film.series_id)
        .subquery()
    )

    total: int = db.query(Series).count()

    rows = (
        db.query(Series, ep_count.c.cnt)
        .outerjoin(ep_count, Series.id == ep_count.c.series_id)
        .order_by(Series.title)
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = [
        SeriesListItem(
            id=s.id,
            title=s.title,
            poster_url=s.poster_url,
            year_start=s.year_start,
            year_end=s.year_end,
            episode_count=cnt or 0,
        )
        for s, cnt in rows
    ]

    return SeriesListResponse(items=items, total=total)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@router.get("/{series_id}", response_model=SeriesDetailOut)
def get_series(series_id: int, db: Session = Depends(get_db)) -> SeriesDetailOut:
    """Return series detail with episodes grouped by season."""
    series = (
        db.query(Series)
        .options(
            joinedload(Series.films)
            .joinedload(Film.editions)
            .joinedload(MovieEdition.media_files)
        )
        .filter(Series.id == series_id)
        .one_or_none()
    )
    if series is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Series not found",
        )

    # Helper to extract the first media ID from a Film's editions
    def _first_media_id(f: Film) -> int | None:
        for ed in f.editions:
            for mf in ed.media_files:
                return mf.id
        return None

    # Group films by season_number (None → treat as season 0)
    by_season: dict[int, list[Film]] = defaultdict(list)
    for f in series.films:
        season = f.season_number if f.season_number is not None else 0
        by_season[season].append(f)

    # Sort seasons by number, then episodes by episode_number within each
    seasons: list[SeasonGroup] = []
    for season_num in sorted(by_season):
        episodes = sorted(by_season[season_num], key=lambda f: f.episode_number or 0)
        seasons.append(
            SeasonGroup(
                season_number=season_num,
                episodes=[
                    EpisodeOut.model_validate(
                        f,
                        from_attributes=True,
                    )
                    for f in episodes
                ],
            )
        )

    # Populate media_id from the first MediaFile of each episode
    ep_by_id: dict[int, EpisodeOut] = {}
    for sg in seasons:
        for ep in sg.episodes:
            ep_by_id[ep.id] = ep

    for f in series.films:
        ep = ep_by_id.get(f.id)
        if ep is not None:
            ep.media_id = _first_media_id(f)

    return SeriesDetailOut(
        id=series.id,
        title=series.title,
        poster_url=series.poster_url,
        year_start=series.year_start,
        year_end=series.year_end,
        created_at=series.created_at,
        seasons=seasons,
        episode_count=len(series.films),
    )


# ---------------------------------------------------------------------------
# Episodes by season
# ---------------------------------------------------------------------------


@router.get("/{series_id}/episodes", response_model=SeriesEpisodesResponse)
def list_episodes(
    series_id: int,
    season: int | None = Query(None, ge=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> SeriesEpisodesResponse:
    """Return paginated episodes for a series, optionally filtered by season."""
    # Verify series exists
    series_exists = db.query(Series.id).filter(Series.id == series_id).first()
    if series_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Series not found",
        )

    query = db.query(Film).filter(Film.series_id == series_id)
    if season is not None:
        query = query.filter(Film.season_number == season)

    total: int = query.count()
    films = (
        query
        .order_by(Film.season_number, Film.episode_number)
        .offset(skip)
        .limit(limit)
        .all()
    )

    return SeriesEpisodesResponse(
        series_id=series_id,
        season_number=season,
        items=[EpisodeOut.model_validate(f) for f in films],
        total=total,
    )
