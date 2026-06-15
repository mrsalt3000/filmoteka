"""Pydantic schemas for catalog endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------


class SeriesOut(BaseModel):
    id: int
    title: str
    poster_url: str | None = None
    year_start: int | None = None
    year_end: int | None = None

    model_config = ConfigDict(from_attributes=True)


class SeriesListItem(BaseModel):
    """Series item for the list endpoint with computed episode count."""

    id: int
    title: str
    poster_url: str | None = None
    year_start: int | None = None
    year_end: int | None = None
    episode_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class SeriesListResponse(BaseModel):
    items: list[SeriesListItem]
    total: int


class EpisodeOut(BaseModel):
    """Lightweight film schema for episode listing."""

    id: int
    title: str
    poster_url: str | None = None
    season_number: int | None = None
    episode_number: int | None = None
    episode_title: str | None = None
    created_at: datetime
    media_id: int | None = None

    model_config = ConfigDict(from_attributes=True)


class SeasonGroup(BaseModel):
    season_number: int
    episodes: list[EpisodeOut]


class SeriesDetailOut(BaseModel):
    """Series detail with episodes grouped by season."""

    id: int
    title: str
    poster_url: str | None = None
    year_start: int | None = None
    year_end: int | None = None
    created_at: datetime
    seasons: list[SeasonGroup]
    episode_count: int


class SeriesEpisodesResponse(BaseModel):
    series_id: int
    season_number: int | None
    items: list[EpisodeOut]
    total: int


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class FilmOut(BaseModel):
    id: int
    title: str
    year: int | None = None
    poster_url: str | None = None
    age_rating: str | None = None
    is_family_video: bool = False
    season_number: int | None = None
    episode_number: int | None = None
    episode_title: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FilmListResponse(BaseModel):
    items: list[FilmOut]
    total: int


# ---------------------------------------------------------------------------
# Detail / card
# ---------------------------------------------------------------------------


class GenreOut(BaseModel):
    id: int
    name: str
    slug: str

    model_config = ConfigDict(from_attributes=True)


class PersonOut(BaseModel):
    id: int
    name: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class MediaFileOut(BaseModel):
    id: int
    file_path: str
    media_alias: str | None = None
    file_size: int | None = None
    duration_secs: float | None = None
    width: int | None = None
    height: int | None = None
    codec: str | None = None

    model_config = ConfigDict(from_attributes=True)


class EditionOut(BaseModel):
    id: int
    edition_name: str | None = None
    quality: str | None = None
    language: str | None = None
    media_files: list[MediaFileOut] = []

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Admin update
# ---------------------------------------------------------------------------


class FilmUpdateSchema(BaseModel):
    title: str | None = None
    year: int | None = None
    description: str | None = None
    age_rating: str | None = None
    is_family_video: bool | None = None
    poster_url: str | None = None
    country: str | None = None


class FilmDetailOut(BaseModel):
    id: int
    title: str
    year: int | None = None
    description: str | None = None
    poster_url: str | None = None
    age_rating: str | None = None
    is_family_video: bool = False
    country: str | None = None
    needs_review: bool = False
    series_id: int | None = None
    season_number: int | None = None
    episode_number: int | None = None
    episode_title: str | None = None
    series: SeriesOut | None = None
    created_at: datetime
    genres: list[GenreOut] = []
    persons: list[PersonOut] = []
    editions: list[EditionOut] = []

    model_config = ConfigDict(from_attributes=True)


class ConflictMediaItem(BaseModel):
    media_id: int
    file_path: str
    media_alias: str | None = None
    file_size: int | None = None
    codec: str | None = None
    audio_codec: str | None = None
    height: int | None = None


class ConflictEditionItem(BaseModel):
    edition_id: int
    quality: str | None = None
    language: str | None = None
    media_files: list[ConflictMediaItem]


class ConflictItem(BaseModel):
    film_id: int
    title: str
    year: int | None = None
    editions: list[ConflictEditionItem]


class ConflictListResponse(BaseModel):
    items: list[ConflictItem]
    total: int
