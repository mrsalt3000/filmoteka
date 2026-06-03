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
- Phase: `initialization`
- Active task: `NONE`
- Last completed task: `INIT-002`
- Current branch: `main`
- Last updated: `2026-06-03`

### Overall status
- Initialization: `10%`
- MVP: `0%`
- V1: `0%`
- V2: `0%`

### Current blockers
- None

### Next recommended tasks
1. INIT-004 — Configure Python project (install deps, verify editable install)
2. INIT-003 — Create docs/test-runbook.md
3. INIT-005 — Set up src layout with empty modules

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
