# Filmoteka — Test Runbook

> Как и когда запускать тесты.

## Prerequisites

```bash
pip install -e ".[dev]"
```

## Quick reference

```bash
# Полный матрикс (ruff → unit → integration → e2e)
bash scripts/run-all-checks.sh

# Только unit
pytest tests/unit -v

# Только integration (требуется Docker Compose: db, redis)
docker compose up -d db redis
pytest tests/integration -v

# Только e2e (требуется полный стек + импортированная библиотека)
pytest tests/e2e -v

# Только coverage (unit + integration)
bash scripts/run-coverage.sh
# → отчёт: file://$(pwd)/htmlcov/index.html

# Acceptance (curl-based, against running stack)
bash scripts/run-acceptance.sh
```

## Test levels

### Unit tests

**Когда:** после изменения доменной логики, parser rules, recommendation
scoring, permission logic, фильтрации, enrichment-функций.

**Что проверяют:** изолированные функции и классы без БД, сети и
файловой системы. Быстрые (~30 сек).

**Команда:**

```bash
pytest tests/unit -v
```

**Текущее покрытие:** 200 тестов (включая FTS, enrichment, auth, catalog).

**Ключевые файлы:**
- `test_deepseek_provider.py` — парсинг ответов DeepSeek (extract + enrich)
- `test_enrichment.py` — upsert жанров/актёров, quality flags, FTS vector
- `test_metadata_providers.py` — OMDB search, title cleaning, type detection
- `test_auth_service.py` — JWT, хеши паролей, age group
- `test_recommendations.py` — scoring, языковой фильтр, genre-based

### Integration tests

**Когда:** после изменений в API, БД, импорте, фоновых задачах,
persistence layer.

**Что проверяют:** взаимодействие компонентов с реальной БД (PostgreSQL),
Redis, файловой системой.

**Требования:**
- PostgreSQL доступен (через Docker Compose)
- Redis доступен

**Команда:**

```bash
docker compose up -d db redis
pytest tests/integration -v
```

**Текущее покрытие:** 273+ тестов (admin + user + catalog + importing + media).

**Ключевые файлы:**
- `test_admin.py` — все admin-эндпоинты (85 тестов)
- `test_catalog.py` — каталог, поиск, фильтры, сериалы
- `test_importing.py` — импорт, дедупликация, TV эпизоды
- `test_media.py` — стриминг, watch, resume
- `test_migrations.py` — проверка миграций
- `test_health.py` — health endpoint
- `test_subtitles.py` — субтитры

> **Известные падения (41):** `test_importing.py` (14) — остаточные данные
> от предыдущих тестов; `test_catalog.py` (7) — аналогично; `test_media.py`
> (2, subtitles); `test_migrations.py` (2) — migration downgrade;
> `test_subtitles.py` (2); `test_health.py` (2); остальные — аналогичные
> проблемы изоляции. Не влияют на production-функциональность.

### E2E tests

**Когда:** после изменений в пользовательских сценариях (каталог,
просмотр, импорт, детские профили).

**Что проверяют:** сквозные пользовательские сценарии через API.

**Требования:**
- Весь стек поднят (Docker Compose: `docker compose up -d`)
- Тестовая библиотека заполнена через `POST /admin/import/scan`

**Команда:**

```bash
pytest tests/e2e -v
```

**Текущее покрытие:** 5 тестов (каталог, плеер, детский профиль,
импорт, рекомендации).

### Acceptance tests

**Когда:** перед релизом, после крупных изменений.

**Что проверяют:** curl-скрипт проверяет все ключевые API-эндпоинты
против запущенного стека.

**Команда:**

```bash
bash scripts/run-acceptance.sh [http://localhost:8000]
```

**Требуется:** `curl`, `jq`.

**Что проверяется:**
- Health check / offline degradation
- Каталог (films + series)
- FTS поиск
- Import scan
- Posters fill-missing
- Aliases generate (если настроен DeepSeek)
- DeepSeek enrichment (если настроен)
- Background jobs + progress endpoints
- Backup

## Code quality

```bash
ruff check src/ tests/     # lint
```

`ruff` чист (0 ошибок на production-коде, несколько предупреждений
в тестовых файлах).

## Coverage

```bash
bash scripts/run-coverage.sh
# → HTML-отчёт: htmlcov/index.html
# → Цель: ~90%
```

Покрытие считается только для `src/filmoteka/`, без `migrations/`.

## CI

На данный момент CI не настроен. Для ручного прогона перед коммитом:

```bash
bash scripts/run-all-checks.sh
```

## Quick cheatsheet

```bash
# Линтер
ruff check src/filmoteka/

# Unit-тесты (быстро)
pytest tests/unit -v --tb=short

# Integration-тесты (требуется Docker)
docker compose up -d db redis
pytest tests/integration/test_admin.py -v --tb=short

# Одна конкретная integration-задача
pytest tests/integration/test_admin.py::TestAdminSuggestDownload -v

# Acceptance (ручной прогон)
bash scripts/run-acceptance.sh

# Coverage
bash scripts/run-coverage.sh
```
