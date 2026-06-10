#!/bin/sh
# Full test matrix: ruff → mypy → unit → integration → e2e
# Exits on first failure.
set -e

echo "========================================="
echo "  Filmoteka — Full test matrix"
echo "========================================="

echo ""
echo "==> [1/5] ruff (linter)"
.venv/bin/ruff check src/ tests/

echo ""
echo "==> [2/5] mypy (type checker)"
.venv/bin/mypy src/ tests/

echo ""
echo "==> [3/5] Unit tests"
.venv/bin/pytest tests/unit/ -v --tb=short

echo ""
echo "==> [4/5] Integration tests"
echo "     (requires PostgreSQL — starting via Docker…)"
docker compose up -d db redis
until docker compose exec db pg_isready -U filmoteka > /dev/null 2>&1; do
  sleep 1
done
.venv/bin/pytest -m integration -v --tb=short

echo ""
echo "==> [5/5] E2E tests"
.venv/bin/pytest tests/e2e/ -v --tb=short

echo ""
echo "========================================="
echo "  All checks passed! 🎉"
echo "========================================="
