# docs/progress.md

# Filmoteka — Progress Log

> Этот файл ведёт агент.
>
> Правила заполнения:
> - После **каждой завершённой задачи** добавлять новую запись в начало файла.
> - Одна запись = одна завершённая задача.
> - Не удалять старые записи.
> - Если задача частично сделана, ставить статус `partial`, а не `done`.
> - Если задача заблокирована, ставить статус `blocked` и обязательно писать причину.
> - Если поведение системы изменилось, агент обязан указать, какие тесты добавлены или обновлены.
> - Если проверки не запускались, нужно явно написать почему.

---

## Current Project Snapshot

### Current phase
- Phase: `mvp`
- Active task: `NONE`
- Last completed task: `MVP-009`
- Current branch: `main`
- Last updated: `2026-06-05`

### Overall status
- Initialization: `100%`
- MVP: `45%`
- V1: `0%`
- V2: `0%`

### Current blockers
- None

### Next recommended tasks
1. MVP-010 — ImportCandidate модель и создание кандидатов при сканировании

---

## Task Report: MVP-009 — 2026-06-05

- Status: `done`
- Summary: Создал ImportRun модель и `scan_downloads()` — рекурсивный обход папки загрузок с фильтром по расширениям, записью ImportRun в БД. 6 unit-тестов (чистая логика сбора файлов) + 3 integration теста.
- Changed files:
  - `src/filmoteka/domain/importing/__init__.py` (new)
  - `src/filmoteka/domain/importing/models.py` (new — ImportRun)
  - `src/filmoteka/domain/importing/scan.py` (new — scan_downloads, _collect_files)
  - `migrations/env.py` (+ importing models)
  - `migrations/versions/41207e590286_add_import_runs_table.py` (new)
  - `tests/unit/test_scan.py` (new — 6 тестов)
  - `tests/integration/test_importing.py` (new — 3 теста)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `pytest tests/unit/ -v` — 53/53 passed
  - `pytest -m integration -v` — 23/23 passed
  - `ruff check src/ tests/` — all checks passed
  - `mypy src/ tests/` — success, 34 source files
- Checks:
  - pytest unit: `yes` (53/53)
  - pytest integration: `yes` (23/23)
  - ruff: `yes`
  - mypy: `yes`
  - alembic upgrade: `yes`
- Risks:
  - scan_downloads пока не создаёт ImportCandidate — будет в MVP-010
- Next task:
  - MVP-010 — ImportCandidate модель и создание кандидатов при сканировании

---

## Task Report: MVP-008 — 2026-06-05

- Status: `done`
- Summary: Перенёс пути `downloads_root` и `target_root` из `.env`/Settings в `library.yaml`/LibraryConfig. Добавил `PathsConfig`, убрал дублирующие поля из Settings. 47 unit-тестов, ruff + mypy чисты.
- Changed files:
  - `specs/library.yaml` (+ paths: downloads_root, target_root)
  - `src/filmoteka/infrastructure/library_config.py` (+ PathsConfig)
  - `src/filmoteka/infrastructure/settings.py` (− downloads_root, library_root)
  - `tests/unit/test_smoke.py` (обновлены проверки)
  - `docs/progress.md` (snapshot + report)
- Checks:
  - pytest unit: `yes` (47/47)
  - ruff: `yes`
  - mypy: `yes`
- Risks:
  - Пути теперь читаются из `library.yaml`, а не из `.env` — docker-compose всё ещё использует свои env-переменные для mount'ов, это не противоречие
- Next task:
  - MVP-009 — ImportRun модель и scan_downloads

---

## Task Report: MVP-007 — 2026-06-05

- Status: `done`
- Summary: Написал 10 unit-тестов для auth service (bcrypt + JWT). Исправил `decode_access_token` — добавил `KeyError` в except для обработки токенов без `sub`. 47 unit-тестов, все проходят, ruff + mypy чисты.
- Changed files:
  - `tests/unit/test_auth_service.py` (new — 10 тестов)
  - `src/filmoteka/domain/access/service.py` (+ KeyError в except)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `pytest tests/unit/ -v` — 47/47 passed
  - `ruff check src/ tests/` — all checks passed
  - `mypy src/ tests/` — success, 29 source files
- Checks:
  - pytest unit: `yes` (47/47)
  - ruff: `yes`
  - mypy: `yes`
- Risks:
  - None
- Next task:
  - MVP-008 — Реализовать чтение путей downloads_root и target_root из library.yaml

---

## Task Report: MVP-006 — 2026-06-05

- Status: `done`
- Summary: Добавил роли `admin` и `user`. Поле `role` в User (default "user"), `require_role()` dependency factory, admin-only endpoint `GET /admin/health`. Миграция добавляет колонку `role` в таблицу users. 4 integration теста на role enforcement.
- Changed files:
  - `src/filmoteka/domain/access/models.py` (+ role column)
  - `src/filmoteka/api/schemas/auth.py` (+ role в UserOut)
  - `src/filmoteka/api/auth.py` (+ require_role, Callable import)
  - `src/filmoteka/api/admin.py` (new — GET /admin/health)
  - `src/filmoteka/app.py` (wired admin_router)
  - `migrations/versions/7f0abe825982_add_role_column_to_users.py` (new)
  - `tests/integration/test_admin.py` (new — 4 теста)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `pytest tests/unit/ -v` — 37/37 passed
  - `pytest -m integration -v` — 20/20 passed
  - `ruff check src/ tests/` — all checks passed
  - `mypy src/ tests/` — success, 28 source files
- Checks:
  - pytest unit: `yes` (37/37)
  - pytest integration: `yes` (20/20)
  - ruff: `yes`
  - mypy: `yes`
  - alembic upgrade: `yes`
- Risks:
  - Роль меняется через БД (UPDATE) — в MVP ещё нет admin-панели, промоушен выполняется вручную
  - `require_role("admin")` — строгое сравнение, не иерархия ролей
- Next task:
  - MVP-007 — Написать тесты auth flow

---

## Task Report: MVP-005 — 2026-06-05

- Status: `done`
- Summary: Реализовал минимальную аутентификацию — регистрация, логин с JWT, endpoint `/auth/me`. User модель (id, username, hashed_password, is_active, created_at), bcrypt для паролей, JWT HS256 с secret_key из settings. 10 integration тестов.
- Changed files:
  - `pyproject.toml` (bcrypt, pyjwt)
  - `src/filmoteka/domain/access/__init__.py` (new)
  - `src/filmoteka/domain/access/models.py` (new — User ORM)
  - `src/filmoteka/domain/access/service.py` (new — hash, verify, JWT)
  - `src/filmoteka/api/schemas/__init__.py` (new)
  - `src/filmoteka/api/schemas/auth.py` (new — RegisterRequest, LoginRequest, TokenResponse, UserOut)
  - `src/filmoteka/api/auth.py` (new — POST /auth/register, POST /auth/login, GET /auth/me)
  - `src/filmoteka/app.py` (wired auth_router)
  - `migrations/env.py` (import access models)
  - `migrations/versions/5e5b30af2aae_add_users_table.py` (new)
  - `tests/integration/test_auth.py` (new — 10 integration тестов)
  - `tests/conftest.py` (увеличил SECRET_KEY до 40 символов для HS256)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `pytest tests/unit/ -v` — 37/37 passed
  - `pytest -m integration -v` — 16/16 passed (6 migration + 10 auth)
  - `ruff check src/ tests/` — all checks passed
  - `mypy src/ tests/` — success, 26 source files
- Checks:
  - pytest unit: `yes` (37/37)
  - pytest integration: `yes` (16/16)
  - ruff: `yes`
  - mypy: `yes`
  - alembic upgrade: `yes`
- Risks:
  - JWT HS256 с `secret_key` из env — при смене ключа все существующие токены станут невалидными
  - Нет refresh token, нет ролей (будет в MVP-006)
  - Нет rate limiting на /auth/login
- Next task:
  - MVP-006 — Реализовать роль `admin` и роль `user`

---

## Task Report: MVP-004 — 2026-06-05

- Status: `done`
- Summary: Создал integration-тесты для миграций и constraints. 6 тестов: lifecycle (apply, roundtrip downgrade, tables exist), cascade delete, unique constraints. Добавлен маркер `integration` — unit-тесты не требуют БД, integration запускаются отдельно через `pytest -m integration`.
- Changed files:
  - `tests/integration/__init__.py` (new)
  - `tests/integration/conftest.py` (new — DB создание/удаление, сессия с rollback, alembic config)
  - `tests/integration/test_migrations.py` (new — 6 integration тестов)
  - `migrations/env.py` (config URL override — уважает уже установленное значение)
  - `pyproject.toml` (добавлен `integration` marker)
  - `scripts/run-integration.sh` (new — `docker compose up -d db && pytest -m integration`)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `pytest tests/unit/ -v` — 37/37 passed (без БД)
  - `pytest -m integration -v` — 6/6 passed (требует PostgreSQL)
  - `ruff check src/ tests/` — all checks passed
  - `mypy src/ tests/` — success, 19 source files
- Checks:
  - pytest unit: `yes` (37/37)
  - pytest integration: `yes` (6/6)
  - ruff: `yes`
  - mypy: `yes`
- Risks:
  - Integration тесты требуют запущенного PostgreSQL (`docker compose up -d db`)
  - `scripts/run-integration.sh` запускает и останавливает контейнер автоматически
  - ALembic env.py изменён: `config.get_main_option("sqlalchemy.url") or settings.database_url` — теперь можно переопределить URL через Config
- Next task:
  - MVP-005 — Реализовать минимального пользователя (регистрация, логин, базовая сессия)

---

## Task Report: MVP-003 — 2026-06-05

- Status: `done`
- Summary: Добавил `ON DELETE CASCADE` на все внешние ключи (6 FK) и недостающие индексы (ix_films_year, ix_movie_editions_film_id, ix_media_files_edition_id). Миграция протестирована round-trip: upgrade → downgrade → upgrade. 2 новых unit-теста.
- Changed files:
  - `src/filmoteka/domain/catalog/models.py` (CASCADE на всех FK + index на year, film_id, edition_id)
  - `migrations/versions/c6dc40f7cf26_add_constraints_and_indexes.py` (new)
  - `tests/unit/test_database.py` (2 теста: single head/base, синтаксис миграций)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `DATABASE_URL=... alembic upgrade head` → 487a45a0f362 → c6dc40f7cf26
  - `DATABASE_URL=... alembic downgrade -1` → 487a45a0f362
  - `DATABASE_URL=... alembic upgrade head` → c6dc40f7cf26
  - `.venv/bin/pytest tests/ -v` — 37/37 passed
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 17 source files
- Checks:
  - pytest: `yes` (37/37)
  - ruff: `yes`
  - mypy: `yes`
  - alembic upgrade: `yes`
  - alembic downgrade: `yes`
  - alembic upgrade again: `yes`
  - psql verify CASCADE: `yes` (все 6 FK с ON DELETE CASCADE)
- Risks:
  - CASCADE удаление — осознанное решение для домашней библиотеки. При удалении фильма уходят все связанные версии, файлы, связи
- Next task:
  - MVP-004 — Написать integration тесты на миграции (апгрейд с чистой БД)

---

## Task Report: MVP-002 — 2026-06-05

- Status: `done`
- Summary: Реализовал core catalog models: Film, Person, Genre, MovieEdition, MediaFile с правильными связями, ассоциативными таблицами и композитными unique constraints. Сгенерирована миграция, применена к PostgreSQL. 17 новых unit-тестов.
- Changed files:
  - `src/filmoteka/domain/catalog/__init__.py` (new)
  - `src/filmoteka/domain/catalog/models.py` (new — 7 таблиц: films, persons, genres, film_genre, film_person, movie_editions, media_files)
  - `migrations/env.py` (import моделей для autogenerate)
  - `migrations/versions/487a45a0f362_add_catalog_models.py` (new — авто-миграция)
  - `tests/unit/test_models.py` (new — 17 тестов: создание, repr, отношения)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `DATABASE_URL=... alembic upgrade head` — init-миграция применена
  - `DATABASE_URL=... alembic revision --autogenerate -m "add catalog models"` — создана
  - `DATABASE_URL=... alembic upgrade head` — применена (7 таблиц в БД)
  - `.venv/bin/pytest tests/ -v` — 35/35 passed
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 17 source files
- Checks:
  - pytest: `yes` (35/35)
  - ruff: `yes`
  - mypy: `yes`
  - alembic upgrade: `yes` (7 tables created)
- Risks:
  - Association tables (film_genre, film_person) без surrogate PK — композитный PK достаточно для M2M
  - subtitle_languages хранится как строка — упрощение для MVP, позже можно вынести в отдельную таблицу
- Next task:
  - MVP-003 — Настроить миграции (индексы, constraints)

---

## Task Report: MVP-001 — 2026-06-05

- Status: `done`
- Summary: Подключил SQLAlchemy 2 и Alembic — database engine, session factory, Alembic env, пустая инициализационная миграция, entrypoint для наката миграций при старте контейнера.
- Changed files:
  - `src/filmoteka/infrastructure/database.py` (new — engine, SessionLocal, Base, get_db)
  - `alembic.ini` (new)
  - `migrations/env.py` (new)
  - `migrations/script.py.mako` (new)
  - `migrations/__init__.py` (new)
  - `migrations/versions/__init__.py` (new)
  - `migrations/versions/bae30842757b_init.py` (new — пустая init-миграция)
  - `docker/entrypoint-api.sh` (new — alembic upgrade head + uvicorn)
  - `docker/Dockerfile.api` (ENTRYPOINT, копирование alembic.ini + migrations/)
  - `docker/Dockerfile.worker` (копирование alembic.ini + migrations/)
  - `migrations/.gitkeep` (removed)
  - `tests/unit/test_database.py` (new — 9 тестов: engine, SessionLocal, Base, Alembic config)
  - `tests/unit/test_smoke.py` (добавлен `type: ignore[call-arg]` для mypy)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/alembic revision -m "init"` — создана пустая миграция
  - `.venv/bin/pytest tests/ -v` — 18/18 passed
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 14 source files
- Checks:
  - pytest: `yes` (18/18)
  - ruff: `yes`
  - mypy: `yes`
- Risks:
  - Для полной проверки `alembic upgrade head` нужен запущенный PostgreSQL — будет проверено в интеграционных тестах (MVP-004) или при `docker compose up`
  - Пул соединений engine — default 5, может потребоваться тюнинг позже
- Next task:
  - MVP-002 — Реализовать core models (Film, Person, Genre)

---

## Task Report: INIT-004 — 2026-06-05

- Status: `done`
- Summary: Created Python virtual environment, installed all runtime and dev dependencies, verified tooling works.
- Changed files:
  - `pyproject.toml` (fixed build-backend from `setuptools.backends._legacy` to `setuptools.build_meta`)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `python3 -m venv .venv` — venv created (ensurepip unavailable, bootstrapped via get-pip.py)
  - `.venv/bin/pip install -e ".[dev]"` — all 44 packages installed
  - `.venv/bin/pytest --collect-only` — 0 tests collected (expected, no tests yet)
  - `.venv/bin/ruff check src/` — no Python files found (expected)
  - `.venv/bin/mypy src/` — no `.py` files (expected)
- Checks:
  - pytest collect: `yes` (no tests — expected at this stage)
  - ruff: `yes` (no files — expected)
  - mypy: `yes` (no files — expected)
  - manual: `yes`
- Risks:
  - Нет собственных тестов для проверки editable install — появится в INIT-015
- Next task:
  - INIT-005 — Set up src layout with empty modules

---

## Task Report: INIT-005 — 2026-06-05

- Status: `done`
- Summary: Created `__init__.py` files in all `src/filmoteka/` subdirectories, removed obsolete `.gitkeep` files.
- Changed files:
  - `src/filmoteka/__init__.py` (new)
  - `src/filmoteka/api/__init__.py` (new)
  - `src/filmoteka/domain/__init__.py` (new)
  - `src/filmoteka/infrastructure/__init__.py` (new)
  - `src/filmoteka/tasks/__init__.py` (new)
  - `src/filmoteka/api/.gitkeep` (removed)
  - `src/filmoteka/domain/.gitkeep` (removed)
  - `src/filmoteka/infrastructure/.gitkeep` (removed)
  - `src/filmoteka/tasks/.gitkeep` (removed)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/python -c "from filmoteka import api, domain, infrastructure, tasks"` — all imports OK
  - `.venv/bin/ruff check src/` — all checks passed
- Checks:
  - import: `yes`
  - ruff: `yes`
  - manual: `yes`
- Risks:
  - None
- Next task:
  - INIT-014 — Set up test structure (conftest, fixtures)

---

## Task Report: INIT-006 — 2026-06-05

- Status: `done`
- Summary: Created minimal FastAPI app bootstrap with health endpoint.
- Changed files:
  - `src/filmoteka/app.py` (new — app factory with FastAPI)
  - `src/filmoteka/api/health.py` (new — `GET /health` route)
  - `src/filmoteka/main.py` (new — uvicorn entry point)
  - `pyproject.toml` (added `[project.scripts]` entry)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/` — all checks passed
  - `.venv/bin/mypy src/` — success, no issues found in 8 source files
  - `uvicorn filmoteka.app:app --port 8081` + `curl localhost:8081/health` — `{"status":"ok","version":"0.1.0"}`
- Checks:
  - ruff: `yes`
  - mypy: `yes`
  - smoke (server + curl): `yes`
  - manual: `yes`
- Risks:
  - None
- Next task:
  - INIT-014 — Set up test structure (conftest, fixtures)

---

## Task Report: INIT-007 — 2026-06-05

- Status: `done`
- Summary: Created docker-compose.yml with all 5 services (db, redis, api, worker, nginx) and nginx reverse proxy config.
- Changed files:
  - `docker-compose.yml` (new)
  - `docker/nginx/default.conf` (new — reverse proxy config)
  - `docker/.gitkeep` (removed)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `docker compose config` — validated successfully, all services resolved
- Checks:
  - docker compose config: `yes`
  - manual: `yes`
- Risks:
  - Dockerfiles (`docker/Dockerfile.api`, `docker/Dockerfile.worker`) ещё не существуют — api и worker не соберутся. Будут созданы в INIT-010.
- Next task:
  - INIT-010 — Create basic Dockerfiles for api and worker

---

## Task Report: INIT-008 — 2026-06-05

- Status: `done`
- Summary: Added healthchecks to db, redis, api services and converted depends_on to conditional startup.
- Changed files:
  - `docker-compose.yml` (healthchecks + depends_on conditions)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `docker compose config` — validated, all healthchecks and conditions resolved
- Checks:
  - docker compose config: `yes`
  - manual: `yes`
- Risks:
  - API healthcheck требует запущенного приложения — не сработает, пока нет Dockerfile (INIT-010)
- Next task:
  - INIT-010 — Create basic Dockerfiles for api and worker

---

## Task Report: INIT-009 — 2026-06-05

- Status: `done`
- Summary: Added bind mounts for downloads and library directories to api and worker services.
- Changed files:
  - `docker-compose.yml` (bind mounts: downloads + library)
  - `.env.example` (DOWNLOADS_ROOT, LIBRARY_ROOT)
  - `.gitignore` (media/)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `docker compose config` — validated, both mounts resolved
- Checks:
  - docker compose config: `yes`
  - manual: `yes`
- Risks:
  - Медиа-директории еще не используются кодом — будут подключены в INIT-011/INIT-012
- Next task:
  - INIT-010 — Create basic Dockerfiles for api and worker

---

## Task Report: INIT-010 — 2026-06-05

- Status: `done`
- Summary: Created Dockerfiles for api and worker, .dockerignore, and verified both images build and serve health endpoint.
- Changed files:
  - `docker/Dockerfile.api` (new — python:3.12-slim, pip install, uvicorn)
  - `docker/Dockerfile.worker` (new — same base, placeholder CMD)
  - `.dockerignore` (new — exclude dev/ci artifacts)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `docker build -t filmoteka-api -f docker/Dockerfile.api .` — ✅ built (28s)
  - `docker run -p 8082:8000 filmoteka-api` + `curl localhost:8082/health` — `{"status":"ok","version":"0.1.0"}`
  - `docker build -t filmoteka-worker -f docker/Dockerfile.worker .` — ✅ built
- Checks:
  - docker build api: `yes`
  - smoke test (curl /health): `yes`
  - docker build worker: `yes`
  - manual: `yes`
- Risks:
  - Worker CMD — заглушка, будет заменён при реализации worker-кода
- Next task:
  - INIT-011 — Implement app settings layer via .env

---

## Task Report: INIT-011 — 2026-06-05

- Status: `done`
- Summary: Created pydantic-settings config layer with env file support, wired into app factory.
- Changed files:
  - `src/filmoteka/infrastructure/settings.py` (new — `Settings` class with 7 fields)
  - `src/filmoteka/app.py` (use `settings.version` for FastAPI title/version)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `ruff check src/` — all checks passed
  - `mypy src/` — success, 9 source files (added `type: ignore[call-arg]` for env-only fields)
  - `python -c "from filmoteka.infrastructure.settings import settings; print(settings.model_dump())"` — all fields loaded
  - `python -c "from filmoteka.app import app; print(app.version)"` — `0.1.0`
- Checks:
  - ruff: `yes`
  - mypy: `yes`
  - settings import: `yes`
  - app bootstrap: `yes`
  - manual: `yes`
- Risks:
  - `type: ignore[call-arg]` — осознанное: `database_url`, `redis_url`, `secret_key` приходят только из env
- Next task:
  - INIT-012 — Implement library.yaml loading

---

## Task Report: INIT-012 — 2026-06-05

- Status: `done`
- Summary: Created library.yaml spec with import rules and organization config, plus pydantic-validated loader.
- Changed files:
  - `specs/library.yaml` (new — extensions, max_file_size, organization rules)
  - `src/filmoteka/infrastructure/library_config.py` (new — `LibraryConfig` model + `load_library_config()`)
  - `specs/.gitkeep` (removed)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `ruff check src/` — all checks passed
  - `mypy src/` — success, 10 source files
  - Happy path: `load_library_config()` — all fields correct
  - Missing file: `FileNotFoundError` — clear message
  - Invalid YAML: pydantic `ValidationError` — readable output
- Checks:
  - ruff: `yes`
  - mypy: `yes`
  - happy path: `yes`
  - file not found: `yes`
  - invalid yaml: `yes`
  - manual: `yes`
- Risks:
  - None
- Next task:
  - INIT-014 — Set up test structure (conftest, fixtures)

---

## Task Report: INIT-013 — 2026-06-05

- Status: `done`
- Summary: Audit of project documentation — all three required files verified complete. Added Commit Convention section to AGENTS.md with TBD rules.
- Changed files:
  - `agents.md` (added `Commit Convention` section, added commit checkbox to Verification Checklist)
  - `docs/progress.md` (snapshot + report)
- Checks:
  - manual: `yes`
- Risks:
  - None
- Next task:
  - INIT-014 — Set up test structure (conftest, fixtures)

---

## Task Report: INIT-014 — 2026-06-05

- Status: `done`
- Summary: Created test infrastructure (conftest with TestClient, test settings override) and first health smoke test.
- Changed files:
  - `tests/conftest.py` (new — env override, TestClient fixture)
  - `tests/unit/conftest.py` (new — package marker)
  - `tests/unit/test_health.py` (new — 2 tests: 200 + 405)
  - `pyproject.toml` (mypy exclude conftest files)
  - `tests/unit/.gitkeep` (removed)
  - `tests/integration/.gitkeep` (removed)
  - `tests/e2e/.gitkeep` (removed)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `pytest tests/ -v` — 2/2 passed
  - `ruff check src/ tests/` — all checks passed
  - `mypy src/ tests/` — success, 11 source files
- Checks:
  - pytest: `yes` (2/2)
  - ruff: `yes`
  - mypy: `yes`
  - manual: `yes`
- Risks:
  - None
- Next task:
  - INIT-015 — Add first smoke tests

---

## Task Report: INIT-015 — 2026-06-05

- Status: `done`
- Summary: Added comprehensive smoke tests — app importability, config validation, and negative test for missing env vars.
- Changed files:
  - `tests/unit/test_smoke.py` (new — 7 tests in 3 classes)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `pytest tests/ -v` — 9/9 passed (2 health + 7 smoke)
  - `ruff check tests/` — all checks passed
  - `mypy tests/` — success, 2 source files
- Checks:
  - pytest: `yes` (9/9)
  - ruff: `yes`
  - mypy: `yes`
- Notes:
  - **Initialization phase complete (100%)** — all 15 INIT tasks done
  - Next phase: **MVP**
- Next task:
  - MVP-001 — Подключить SQLAlchemy и Alembic

---

## Task Report: INIT-001 — 2026-06-03

- Status: `done`
- Summary: Created repository skeleton — all required directories with `.gitkeep` files.
- Changed files:
  - `src/filmoteka/api/.gitkeep`
  - `src/filmoteka/domain/.gitkeep`
  - `src/filmoteka/infrastructure/.gitkeep`
  - `src/filmoteka/tasks/.gitkeep`
  - `tests/unit/.gitkeep`
  - `tests/integration/.gitkeep`
  - `tests/e2e/.gitkeep`
  - `docker/.gitkeep`
  - `specs/.gitkeep`
  - `migrations/.gitkeep`
  - `scripts/.gitkeep`
  - `docs/progress.md` (updated snapshot + report)
- Commands run:
  - `mkdir -p src/filmoteka/{api,domain,infrastructure,tasks} tests/{unit,integration,e2e} docker specs migrations scripts`
  - `touch .../.gitkeep` for each directory
  - `ls -d` all directories — confirmed
  - `find ... -name .gitkeep` — all 11 present
  - `git status --short` — only new directories
- Checks:
  - manual: `yes`
- Risks:
  - None
- Next task:
  - INIT-002 — Create service files

## Task Report: INIT-002 — 2026-06-03

- Status: `done`
- Summary: Created basic service files — README.md, .gitignore, .env.example, pyproject.toml.
- Changed files:
  - `README.md`
  - `.gitignore`
  - `.env.example`
  - `pyproject.toml`
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `python3 -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb'))"` — valid TOML
  - `grep -c '__pycache__\|\.env\$\|\.venv' .gitignore` — all 3 patterns present
  - `grep` for secret patterns in `.env.example` — none found
- Checks:
  - manual: `yes`
- Risks:
  - Нужно будет актуализировать зависимости при добавлении новых модулей
- Next task:
  - INIT-004 — Configure Python project

## Task Report: INIT-003 — 2026-06-03

- Status: `done`
- Summary: Created docs/test-runbook.md with instructions for unit, integration, and e2e test levels.
- Changed files:
  - `docs/test-runbook.md`
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `ls docs/test-runbook.md` — exists
- Checks:
  - manual: `yes`
- Risks:
  - runbook нужно будет актуализировать при появлении conftest, фикстур и Docker Compose
- Next task:
  - INIT-004 — Configure Python project

---

## Entry Template

> Скопируй этот блок для новой записи и заполни его.

## Task Report: <TASK-ID> — <YYYY-MM-DD HH:MM>

### Status
- `done | partial | blocked`

### Summary
Коротко: что именно сделано в рамках задачи.

### Goal
Какую цель решала задача.

### Scope
Что входило в задачу:
- ...
- ...
- ...

Что **не** входило в задачу:
- ...
- ...

### Changed files
- `path/to/file1`
- `path/to/file2`
- `path/to/file3`

### New files
- `path/to/new_file1`
- `path/to/new_file2`

### Implementation notes
Основные решения по реализации:
- ...
- ...
- ...

### Commands run
```bash
<command 1>
<command 2>
<command 3>
```

### Verification
Как проверяли результат:
1. ...
2. ...
3. ...

### Check results
- [ ] format
- [ ] lint
- [ ] typecheck
- [ ] unit
- [ ] integration
- [ ] e2e
- [ ] manual check

### Test details
Добавленные или изменённые тесты:
- ...
- ...

Что именно покрыто тестами:
- ...
- ...

Что ещё не покрыто:
- ...
- ...

### Result
Что получилось в итоге:
- ...
- ...
- ...

### Risks / follow-ups
Оставшиеся риски, хвосты или спорные моменты:
- ...
- ...
- ...

### Blockers
Если задача не завершена, указать причину:
- None

### Next recommended task
- <NEXT-TASK-ID> — <short description>

### Agent self-check
- [ ] Сделана только одна задача
- [ ] Изменения ограничены scope задачи
- [ ] Обновлены или добавлены тесты, если менялось поведение
- [ ] Выполнены релевантные проверки
- [ ] Не было незапрошенного большого рефакторинга
- [ ] Запись в `docs/progress.md` заполнена полностью

---

## Progress Entries

## Task Report: PROJECT-BOOTSTRAP — YYYY-MM-DD HH:MM

### Status
- `partial`

### Summary
Стартовый шаблон журнала создан.

### Goal
Подготовить единый журнал, который агент будет дополнять после каждой задачи.

### Scope
Что входило в задачу:
- создать шаблон `docs/progress.md`
- определить единый формат task report
- добавить секции для проверок, тестов и хвостов

Что **не** входило в задачу:
- реализация кода приложения
- обновление tasklist
- создание миграций, API или UI

### Changed files
- `docs/progress.md`

### New files
- `docs/progress.md`

### Implementation notes
Основные решения по реализации:
- запись делается в markdown, чтобы файл было удобно читать человеку и агенту
- каждая задача оформляется отдельным блоком `Task Report`
- добавлены чекбоксы проверок для прозрачности качества
- добавлен `Current Project Snapshot`, чтобы агенту было проще ориентироваться в текущем состоянии проекта

### Commands run
```bash
# not applicable
```

### Verification
Как проверяли результат:
1. Проверен формат markdown.
2. Проверена полнота шаблона.
3. Проверено, что файл можно использовать как append-only журнал.

### Check results
- [ ] format
- [ ] lint
- [ ] typecheck
- [ ] unit
- [ ] integration
- [ ] e2e
- [x] manual check

### Test details
Добавленные или изменённые тесты:
- Нет, документальный файл.

Что именно покрыто тестами:
- Не применимо.

Что ещё не покрыто:
- Не применимо.

### Result
Что получилось в итоге:
- подготовлен единый шаблон progress log
- агент может использовать файл как рабочий журнал
- структура подходит для initialization, mvp, v1 и v2 задач

### Risks / follow-ups
Оставшиеся риски, хвосты или спорные моменты:
- агент должен строго соблюдать правило "одна задача — одна запись"
- желательно позже синхронизировать `Current Project Snapshot` с реальным прогрессом по tasklist

### Blockers
Если задача не завершена, указать причину:
- None

### Next recommended task
- INIT-001 — Create repository skeleton

### Agent self-check
- [x] Сделана только одна задача
- [x] Изменения ограничены scope задачи
- [x] Обновлены или добавлены тесты, если менялось поведение
- [x] Выполнены релевантные проверки
- [x] Не было незапрошенного большого рефакторинга
- [x] Запись в `docs/progress.md` заполнена полностью

---

## Lightweight Entry Template

> Короткая версия, если не нужна полная форма. Использовать только для маленьких инфраструктурных задач.

## Task Report: <TASK-ID> — <YYYY-MM-DD HH:MM>

- Status: `done | partial | blocked`
- Summary: ...
- Changed files:
  - `...`
- Commands run:
  - `...`
- Checks:
  - format: `yes/no`
  - lint: `yes/no`
  - typecheck: `yes/no`
  - unit: `yes/no`
  - integration: `yes/no`
  - e2e: `yes/no`
  - manual: `yes/no`
- Risks:
  - ...
- Next task:
  - ...

---

## Conventions

### Status values
- `done` — задача завершена полностью
- `partial` — выполнена только часть задачи
- `blocked` — задача остановлена из-за внешней причины или архитектурного стоп-фактора

### What counts as verification
Подходящие варианты:
- запуск unit tests
- запуск integration tests
- ручная проверка endpoint-а
- ручная проверка UI-сценария
- проверка миграции на чистой БД
- smoke-запуск через Docker Compose

### What must be listed in Changed files
Нужно перечислять:
- production code
- test files
- config files
- migrations
- docs, если они менялись в рамках задачи

Не нужно перечислять:
- временные файлы
- локальные editor files
- кэш
- артефакты виртуального окружения

### Rule for tests
Если задача меняет:
- бизнес-логику,
- API,
- поведение импорта,
- рекомендации,
- ограничения профилей,
- формат БД,

то агент должен:
1. либо добавить/обновить тесты,
2. либо явно написать, почему тесты сейчас не добавлены.

### Rule for unfinished work
Если работа не завершена:
- не писать `done`
- обязательно перечислить, что осталось
- рекомендовать следующую задачу так, чтобы она логично завершала текущую

### Rule for large tasks
Если задача оказалась слишком большой:
- остановиться,
- отметить `partial`,
- зафиксировать уже сделанное,
- предложить разбиение на подзадачи.
