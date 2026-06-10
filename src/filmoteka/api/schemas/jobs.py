"""Pydantic schemas for background job status."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class JobStatusResponse(BaseModel):
    id: int
    type: str
    status: str
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    result: dict | None = None
