"""Pydantic schemas for catalog endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


class FilmOut(BaseModel):
    id: int
    title: str
    year: int | None = None
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


class FilmDetailOut(BaseModel):
    id: int
    title: str
    year: int | None = None
    description: str | None = None
    created_at: datetime
    genres: list[GenreOut] = []
    persons: list[PersonOut] = []
    editions: list[EditionOut] = []

    model_config = ConfigDict(from_attributes=True)
