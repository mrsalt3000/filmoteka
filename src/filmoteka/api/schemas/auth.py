"""Pydantic schemas for authentication endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

VALID_ROLES = frozenset({"user", "child"})
VALID_AGE_GROUPS = frozenset({"0_6", "7_12", "13_17"})


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=128)
    password: str = Field(min_length=4, max_length=256)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    incognito: bool = False
    age_group: str | None = None
    exclude_family_from_recommendations: bool = True
    exclude_watched: bool = False
    include_external: bool = False
    filter_by_language: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=2, max_length=128)
    password: str = Field(min_length=4, max_length=256)
    role: str = Field(default="user")
    age_group: str | None = None


class AdminUpdateUserRequest(BaseModel):
    age_group: str | None = None
