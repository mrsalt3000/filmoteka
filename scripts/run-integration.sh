#!/bin/sh
set -e

echo "==> Starting PostgreSQL..."
docker compose up -d db

echo "==> Waiting for PostgreSQL to be healthy..."
until docker compose exec db pg_isready -U filmoteka > /dev/null 2>&1; do
  sleep 1
done

echo "==> Running integration tests..."
.venv/bin/pytest -m integration -v --tb=short "$@"

echo "==> Stopping PostgreSQL..."
docker compose down db
