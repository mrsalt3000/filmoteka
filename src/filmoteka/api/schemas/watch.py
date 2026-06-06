"""Pydantic schemas for watch endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WatchStartResponse(BaseModel):
    watch_event_id: int
    media_file_id: int
    started_at: datetime
    last_position: float
    finished: bool


class WatchProgressRequest(BaseModel):
    position: float


class WatchStateResponse(BaseModel):
    has_state: bool
    watch_event_id: int | None = None
    media_file_id: int | None = None
    started_at: datetime | None = None
    last_position: float | None = None
    finished: bool | None = None


class WatchHistoryItem(BaseModel):
    watch_event_id: int
    media_file_id: int
    film_id: int
    film_title: str
    film_year: int | None = None
    started_at: datetime
    last_position: float
    finished: bool


class WatchHistoryResponse(BaseModel):
    items: list[WatchHistoryItem]
    total: int
