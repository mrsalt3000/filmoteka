#!/bin/sh
# Coverage report: unit + integration tests (excluding e2e)
set -e

echo "========================================="
echo "  Filmoteka — Coverage report"
echo "========================================="

echo ""
echo "==> Starting PostgreSQL (if not already running)…"
docker compose up -d db redis
until docker compose exec db pg_isready -U filmoteka > /dev/null 2>&1; do
  sleep 1
done

echo ""
echo "==> Running unit + integration tests with coverage…"
.venv/bin/pytest tests/unit/ tests/integration/ \
  --cov=filmoteka \
  --cov-report=html \
  --cov-report=term-missing \
  -v --tb=short

echo ""
echo "==> HTML report: file://$(pwd)/htmlcov/index.html"
echo ""
echo "========================================="
echo "  Coverage report generated! 🎉"
echo "========================================="
