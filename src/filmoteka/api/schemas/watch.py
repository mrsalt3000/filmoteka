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
