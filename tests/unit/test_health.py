"""Unit tests for the public /health endpoint."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from filmoteka.infrastructure.settings import settings


class TestHealth:
    def test_health_returns_ok(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "2.0.0"
        assert "database" in data
        assert "external" in data

    def test_health_without_omdb_key(self, client: TestClient) -> None:
        with patch.object(settings, "omdb_api_key", None):
            response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["external"]["status"] == "ok"  # no key → no check

    def test_health_method_not_allowed(self, client: TestClient) -> None:
        response = client.post("/health")
        assert response.status_code == 405
