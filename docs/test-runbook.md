# Filmoteka — Test Runbook

> Как и когда запускать тесты.

## Prerequisites

```bash
pip install -e ".[dev]"
```

## Quick reference

```bash
# Полный матрикс (ruff → mypy → unit → integration → e2e)
bash scripts/run-all-checks.sh

# Только coverage (unit + integration)
bash scripts/run-coverage.sh
# → отчёт: file://$(pwd)/htmlcov/index.html
```

## Test levels

### Unit tests

**Когда:** после изменения доменной логики, parser rules, recommendation
scoring, permission logic.

**Что проверяют:** изолированные функции и классы без БД, сети и
файловой системы. Быстрые (~30 сек).

**Команда:**

```bash
pytest tests/unit -v
```

**Текущее покрытие:** 144 теста.

### Integration tests

**Когда:** после изменений в API, БД, импорте, фоновых задачах,
persistence layer.

**Что проверяют:** взаимодействие компонентов с реальной БД (PostgreSQL),
Redis, файловой системой.

**Требования:**
- PostgreSQL доступен (локально или через Docker)
- Redis доступен
- Переменные окружения для тестовой БД можно задать через `.env`

**Команда:**

```bash
# Через Docker
docker compose up -d db redis
pytest tests/integration -v

# Или через маркер (если стек уже поднят)
pytest -m integration -v
```

**Текущее покрытие:** 214+ тестов (admin + user + catalog + importing).

> **Известные падения (21):** `test_catalog.py` — проблемы изоляции
> (остаточные данные от предыдущих тестов); `test_importing.py` —
> аналогично; `test_migrations.py` — downgrade миграции
> `change_size_to_bigint` (NumericValueOutOfRange). Не влияют на
> production-функциональность.

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

## Code quality

```bash
ruff check src/ tests/     # lint
mypy src/ tests/           # type checks
```

`ruff` имеет ~12 предсуществующих предупреждений в тестовых файлах
(не-sorted imports, line length) — не блокирующие.

## Continuous Integration

На данный момент CI не настроен. Для ручного прогона перед коммитом:

```bash
bash scripts/run-all-checks.sh
```

Останавливается на первой ошибке (`set -e`).

## Coverage

```bash
bash scripts/run-coverage.sh
# → HTML-отчёт: htmlcov/index.html
# → Текущий уровень: ~90% (1942 stmts, 199 missing)
```

Покрытие считается только для `src/filmoteka/`, без `migrations/`.
