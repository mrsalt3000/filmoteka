#!/bin/sh
set -e

echo "Running pending migrations..."
alembic upgrade head

echo "Starting uvicorn..."
exec uvicorn filmoteka.app:app --host 0.0.0.0 --port 8000
