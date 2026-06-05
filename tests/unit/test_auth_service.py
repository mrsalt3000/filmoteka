"""Unit tests for the authentication service layer (no database required)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from filmoteka.domain.access.service import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from filmoteka.infrastructure.settings import settings

ALGORITHM = "HS256"


class TestPasswordHashing:
    """bcrypt hashing and verification."""

    def test_hash_password_roundtrip(self) -> None:
        hashed = hash_password("my_secret_p4ss")
        assert verify_password("my_secret_p4ss", hashed) is True

    def test_verify_password_wrong(self) -> None:
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_verify_password_empty(self) -> None:
        hashed = hash_password("somepass")
        assert verify_password("", hashed) is False

    def test_hash_is_deterministically_different(self) -> None:
        """bcrypt salts each hash, so two hashes of the same password differ."""
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        assert h1 != h2


class TestJWTToken:
    """JWT creation and decoding."""

    def test_create_and_decode_token(self) -> None:
        user_id = 42
        token = create_access_token(user_id)
        decoded = decode_access_token(token)
        assert decoded == user_id

    def test_decode_invalid_token_returns_none(self) -> None:
        assert decode_access_token("not.a.token") is None

    def test_decode_empty_token_returns_none(self) -> None:
        assert decode_access_token("") is None

    def test_decode_expired_token_returns_none(self) -> None:
        """A token with expiry in the past must be rejected."""
        payload = {
            "sub": "1",
            "exp": datetime.now(UTC) - timedelta(hours=1),
        }
        expired_token = jwt.encode(
            payload, settings.secret_key, algorithm=ALGORITHM
        )
        assert decode_access_token(expired_token) is None

    def test_decode_token_wrong_signature_returns_none(self) -> None:
        """A token signed with a different key must be rejected."""
        payload = {"sub": "1", "exp": datetime.now(UTC) + timedelta(hours=1)}
        wrong_key_token = jwt.encode(
            payload, "some-other-secret-key", algorithm=ALGORITHM
        )
        assert decode_access_token(wrong_key_token) is None

    def test_decode_token_missing_sub_returns_none(self) -> None:
        """A token without the 'sub' claim must be rejected."""
        payload = {"exp": datetime.now(UTC) + timedelta(hours=1)}
        token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
        assert decode_access_token(token) is None
