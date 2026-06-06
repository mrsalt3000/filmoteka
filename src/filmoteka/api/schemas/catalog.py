"""Pydantic schemas for catalog endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FilmOut(BaseModel):
    id: int
    title: str
    year: int | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FilmListResponse(BaseModel):
    items: list[FilmOut]
    total: int
