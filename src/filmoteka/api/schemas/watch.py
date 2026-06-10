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


class FilmWatchState(BaseModel):
    has_state: bool
    last_position: float | None = None
    duration_secs: float | None = None
    finished: bool | None = None


class FilmWatchStatesRequest(BaseModel):
    film_ids: list[int]


class FilmWatchStatesResponse(BaseModel):
    states: dict[str, FilmWatchState]


class RecommendationItem(BaseModel):
    film_id: int
    title: str
    year: int | None = None
    poster_url: str | None = None
    score: float = 0.0
    match_reason: str = ""


class RecommendationsResponse(BaseModel):
    items: list[RecommendationItem]
    total: int


class MoodQueryRequest(BaseModel):
    query: str


class ComponentStatus(BaseModel):
    status: str  # ok | degraded | unavailable


class HealthResponse(BaseModel):
    status: str
    database: ComponentStatus
    external: ComponentStatus
    version: str = "2.0.0"


class AdminWatchStatItem(BaseModel):
    user_id: int
    username: str
    film_title: str
    started_at: datetime
    finished: bool


class AdminWatchStatsResponse(BaseModel):
    items: list[AdminWatchStatItem]
    total: int


class AdminWatchStatsSummaryItem(BaseModel):
    user_id: int
    username: str
    films_started: int


class AdminWatchStatsSummaryResponse(BaseModel):
    items: list[AdminWatchStatsSummaryItem]
    total: int
