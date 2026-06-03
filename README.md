# Filmoteka

Домашний видео хостинг над локальным киноархивом.

## Stack

- Python + FastAPI
- PostgreSQL
- Redis
- Docker Compose

## Quick start

```bash
cp .env.example .env
# edit .env with your paths and secrets

docker compose up --build
```

## Project layout

```
src/filmoteka/       — backend source
  api/               — HTTP route handlers
  domain/            — domain logic
  infrastructure/    — db, config, filesystem
  tasks/             — background jobs
tests/
  unit/              — unit tests
  integration/       — integration tests
  e2e/               — end-to-end tests
docker/              — Dockerfiles, compose
specs/               — business config (library.yaml)
migrations/          — Alembic migrations
scripts/             — utility scripts
docs/                — project docs
```
