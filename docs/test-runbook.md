# Filmoteka — Test Runbook

> Как и когда запускать тесты.

## Prerequisites

```bash
pip install -e ".[dev]"
```

## Test levels

### Unit tests

**Когда**: после изменения доменной логики, parser rules, recommendation scoring, permission logic.

**Что проверяют**: изолированные функции и классы без БД, сети и файловой системы.

**Команда**:

```bash
pytest tests/unit -v
```

### Integration tests

**Когда**: после изменений в API, БД, импорте, фоновых задачах, persistence layer.

**Что проверяют**: взаимодействие компонентов с реальной БД (PostgreSQL), Redis, файловой системой.

**Требования**:
- PostgreSQL доступен (локально или через Docker)
- Redis доступен
- Переменные окружения для тестовой БД можно задать через `.env.test`

**Команда**:

```bash
pytest tests/integration -v
```

### E2E tests

**Когда**: после изменений в пользовательских сценариях (каталог, просмотр, импорт, детские профили).

**Что проверяют**: сквозные пользовательские сценарии через реальный API/UI.

**Требования**:
- Весь стек поднят (Docker Compose)
- Тестовая библиотека заполнена

**Команда**:

```bash
pytest tests/e2e -v
```

## Quick all

```bash
pytest tests/ -v
```

При этом e2e-тесты должны быть помечены (`pytest.mark.e2e`) и пропускаться, если стек не поднят.

## Code quality

```bash
ruff check src/           # lint
ruff format --check src/  # formatting
mypy src/                 # type checks
```
