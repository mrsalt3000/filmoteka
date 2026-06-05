# AGENTS.md

This file provides guidance to Qwen Code when working with code in this repository.

# Filmoteka

Домашний видео хостинг над локальным киноархивом.

Цель проекта:
- хранить локальную библиотеку фильмов;
- импортировать новые файлы из папки загрузок;
- показывать каталог и карточки фильмов в браузере;
- воспроизводить локальные файлы;
- хранить историю просмотров;
- давать персональные рекомендации;
- поддерживать детские профили, family video и офлайн-устойчивость.

---

## Working Principles

### Simplicity First

Пиши минимальный код, который решает задачу.

- Не добавляй фичи "на будущее".
- Не вводи абстракции без реальной потребности.
- Не делай "гибкость", если она не нужна прямо сейчас.
- Не усложняй import pipeline, API или модели без причины.
- Если решение можно сделать проще без потери смысла — упрощай. [page:1]

Проверочный вопрос:
> Это решение одобрил бы сильный senior как достаточно простое для текущей задачи?

Если нет — упростить.

### One Task Per Iteration

Всегда делай только **одну задачу за итерацию**.

- Не захватывай соседние задачи.
- Не делай попутные рефакторы без отдельного запроса.
- Если задача оказалась слишком большой — остановись, зафиксируй `partial`, предложи разбиение.

### Small Safe Changes

Предпочитай маленькие, проверяемые изменения.

- Сначала минимальный рабочий результат.
- Потом проверка.
- Потом отчёт.
- Потом переход к следующей задаче.

### Behavior Changes Require Tests

Если меняется поведение системы, добавь или обнови тесты.

Это особенно обязательно для:
- импорта;
- дедупликации;
- API;
- playback state;
- рекомендаций;
- child restrictions;
- history/incognito;
- metadata enrichment.

---

## Project Architecture

### High-level choice

На старте проект строится как **модульный монолит**.

Не раскалывай систему на микросервисы без явной необходимости.

### Core stack

- Python
- FastAPI
- PostgreSQL
- Redis
- Docker Compose

### Repository layout

Используется `src layout`.

```text
src/
  filmoteka/
tests/
docker/
specs/
docs/
migrations/
.qwen/
```

Исходный код живёт только под `src/filmoteka/`.

### Domain boundaries

Соблюдай разделение по доменам, а не по "слоям ради слоёв".

Пример ожидаемых модулей:
- `domain/catalog`
- `domain/importing`
- `domain/metadata`
- `domain/watching`
- `domain/recommendations`
- `domain/access`
- `api`
- `infrastructure`
- `tasks`

Не смешивай:
- HTTP-роуты,
- бизнес-логику,
- работу с БД,
- файловую систему,
- внешние интеграции.

---

## Hard Invariants

Эти инварианты нельзя ломать без отдельного архитектурного решения.

### 1. Movie != Edition != Media File

Разделяй:
- `movie` — произведение;
- `movie_edition` — версия/релиз/перевод/режиссёрская версия;
- `media_file` — конкретный физический файл.

Нельзя схлопывать это в одну сущность.

### 2. Import must be idempotent

Повторный импорт не должен:
- плодить дубли;
- ломать уже импортированную библиотеку;
- терять связи;
- затирать валидные данные без явного правила.

### 3. Offline library must still work

Если интернет, Kinopoisk, TMDb или LLM недоступны:
- каталог должен открываться;
- локальный поиск должен работать по уже имеющимся данным;
- локальное воспроизведение должно работать;
- enrichment-задачи могут откладываться, но core product не должен падать.

### 4. Secrets and product rules are separate

- Секреты: `.env`
- Бизнес-правила и пути: `specs/library.yaml`

Никогда не клади секреты в `library.yaml`.

### 5. Background work must not block API

Тяжёлые процессы должны выполняться вне request path:
- импорт;
- enrichment;
- постеры;
- внешние ссылки;
- пересчёт рекомендаций;
- реиндексация.

---

## Required Workflow

Для любой задачи соблюдай этот порядок.

### 1. Read context

Перед работой прочитай:
- `AGENTS.md`
- `agent-tasklist.md`
- `docs/progress.md`
- `docs/architecture-decisions.md`

Если задача сложная, сначала уточни, какая именно task ID берётся в работу.

### 2. Pick exactly one task

Выбери только одну задачу из backlog.

Если у задачи есть prereqs — сначала проверь, что они выполнены.

### 3. Make a short plan

До изменений коротко опиши:
- что будешь делать;
- какие файлы вероятно изменятся;
- какие проверки запустишь.

### 4. Implement the smallest valid change

Сделай минимальный рабочий объём.

Не добавляй соседние улучшения "раз уж был рядом".

### 5. Run checks

Запусти только релевантные проверки.

Минимум зависит от типа задачи:
- docs-only: manual check;
- pure logic: unit tests;
- API/db behavior: unit + integration;
- UI/user flow: e2e or manual scenario;
- migrations: migration check + integration;
- import pipeline: unit + integration with temp files.

### 6. Write task report

После задачи обнови `docs/progress.md`:
- что сделано;
- какие файлы изменены;
- как проверяли;
- какой результат;
- какие хвосты остались;
- какая следующая задача рекомендуется.

### 7. Stop

После одной задачи — остановиться.

Не переходить к следующей автоматически.

---

## Task Execution Rules

### Allowed by default

Можно без отдельного согласования:
- создавать новые файлы в рамках задачи;
- обновлять тесты в рамках задачи;
- менять docs, если это нужно для завершения задачи;
- добавлять минимально необходимую инфраструктуру.

### Not allowed by default

Нельзя без явного запроса:
- массово переименовывать файлы;
- делать большой рефакторинг нескольких доменов сразу;
- менять архитектурные инварианты;
- менять стек;
- удалять большие куски кода "для красоты";
- вносить unrelated fixes.

### When blocked

Если задача блокируется:
- не импровизируй архитектурно;
- не принимай скрыто большие решения;
- зафиксируй `blocked` или `partial`;
- коротко опиши, что мешает;
- предложи 1–3 конкретных варианта продолжения.

---

## Code Style Rules

### General

- Предпочитай читаемый, прямой код.
- Избегай чрезмерной магии.
- Используй явные имена.
- Комментарии добавляй только когда без них непонятно **почему**, а не **что** делает код. [page:1]

### Python

- Следовать типизации там, где это даёт ценность.
- Не использовать огромные utility-модули "на все случаи".
- Не смешивать ORM-модели и API-схемы в одном месте.
- Не класть бизнес-логику в FastAPI route handlers.

### Database

- Все изменения схемы делать через миграции.
- Не править схему вручную как постоянный способ работы.
- Ограничения целостности предпочитать на уровне БД, а не только в коде.

### API

- API должен быть скучным и предсказуемым.
- Явные request/response схемы.
- Не тащить доменную логику в сериализаторы.
- Админские действия должны быть отделены от пользовательских.

### Frontend

- Не делать сложный frontend framework-first дизайн раньше времени.
- Сначала обеспечить рабочий каталог, карточку, плеер, историю.
- UI должен объяснять состояния:
  - loading,
  - empty,
  - error,
  - conflict,
  - no metadata,
  - offline degraded mode.

---

## Commit Convention

Проект следует **Trunk-Based Development (TBD)** — маленькие атомарные коммиты, частые пуши в `main`.

### Правила

1. **Формат сообщения:** `type: краткое описание`
   - Допустимые `type`: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`
   - Subject — до 72 символов, без точки в конце
2. **Тело коммита:** номер задачи в формате `TASK-ID: описание`
3. **Стейжинг:** только файлы, относящиеся к задаче. Не включать `.qwen/settings.json`, `.qwen/settings.json.orig` и другие локальные артефакты.
4. **Push:** сразу после коммита.

### Примеры

```
feat: add minimal FastAPI app bootstrap

INIT-006: create app factory, health endpoint, and scripts entry
```

```
chore: configure Python project environment

INIT-004: create venv, install dependencies, fix build-backend
```

---

## Testing Strategy

Тесты делятся на три уровня:

```text
tests/unit
tests/integration
tests/e2e
```

### Unit tests

Использовать для:
- доменной логики;
- parser logic;
- recommendation scoring;
- metadata normalization;
- permission rules;
- path generation;
- dedup rules.

### Integration tests

Использовать для:
- БД и миграций;
- API endpoints;
- import pipeline с временными файлами;
- background jobs;
- config loading;
- persistence rules.

### E2E tests

Использовать для пользовательских сценариев:
- открыть каталог;
- открыть карточку;
- начать просмотр;
- resume playback;
- child restrictions;
- import admin flow;
- recommendation flow.

### Test discipline

- Не заменяй unit tests integration-тестами без причины.
- Не делай e2e там, где достаточно unit/integration.
- Если тесты не добавлены, явно объясни почему.

---

## Verification Checklist

Перед тем как пометить задачу как завершённую, проверь:

- [ ] задача одна, scope не расплылся;
- [ ] код соответствует текущему этапу проекта;
- [ ] изменены только нужные файлы;
- [ ] добавлены/обновлены тесты, если поведение изменилось;
- [ ] выполнены релевантные проверки;
- [ ] коммит следует TBD-формату: `type: описание` + `TASK-ID: ...` в теле;
- [ ] обновлён `docs/progress.md`;
- [ ] если было архитектурное решение — обновлён `docs/architecture-decisions.md`.

---

## Project Files

### Must know

- `agent-tasklist.md` — основной backlog
- `docs/progress.md` — журнал выполнения задач
- `docs/architecture-decisions.md` — журнал архитектурных решений
- `specs/library.yaml` — бизнес-конфиг библиотеки
- `.env` — секреты и environment-specific значения

### `.qwen/` directories

Используй `.qwen/` для рабочих артефактов:

- `.qwen/design/` — design docs для нетривиальных изменений
- `.qwen/e2e-tests/` — планы и результаты e2e сценариев
- `.qwen/investigations/` — debugging journals
- `.qwen/pr-drafts/` — черновики PR
- `.qwen/pr-reviews/` — заметки по review
- `.qwen/scripts/` — утилитарные скрипты [page:1]

---

## Design Doc Rule

Если задача:
- затрагивает несколько доменов,
- меняет важный data flow,
- вводит новый pipeline,
- меняет import/recommendation architecture,
- трогает offline behavior,

то сначала создай design doc в `.qwen/design/`.

Design doc не должен быть огромным. Достаточно:
- проблема,
- ограничения,
- proposed solution,
- alternatives,
- risks,
- verification plan.

---

## Special Guidance By Area

### Import pipeline

Будь особенно осторожен.

Всегда помнить:
- импорт идемпотентен;
- пути могут быть грязными;
- метаданные из имени файла ненадёжны;
- физическое перемещение файла и запись в БД должны быть согласованы;
- конфликт не должен silently merge-иться в неверный фильм.

### Metadata enrichment

Внешние данные ненадёжны.

Всегда хранить:
- source,
- confidence,
- updated_at,
- needs_review.

Ручная правка админом должна быть возможна без SQL.

### Recommendations

Рекомендации всегда подчиняются ограничениям:
- child restrictions,
- blacklist,
- incognito exclusion from history,
- exclude watched toggle,
- exclude family video toggle,
- language filters.

### Playback and history

Нужно поддерживать:
- start event,
- progress updates,
- resume playback,
- clear history,
- incognito mode.

Инкогнито не должно влиять на рекомендации.

---

## What “Done” Means

Задача считается завершённой, если:
1. Реализация готова в пределах scope.
2. Проверки выполнены.
3. Тесты добавлены или обновлены, если это требовалось.
4. `docs/progress.md` обновлён.
5. Нет скрытых незадокументированных хвостов.

Если любой из пунктов не выполнен — задача не `done`.

---

## Output Format After Each Task

После каждой задачи агент должен показать:

1. **Task ID**
2. **What changed**
3. **Changed files**
4. **Checks run**
5. **Result**
6. **Risks / follow-ups**
7. **Recommended next task**

---

## First Priority Order

Если непонятно, с чего начинать, придерживайся такого порядка:

1. Initialization
2. Database and config foundation
3. Import MVP
4. Catalog MVP
5. Playback/history MVP
6. Search MVP
7. Metadata enrichment
8. Filters and profiles
9. Recommendations
10. Offline degradation
11. Backup/restore
12. Final acceptance

---

## Final Reminder

Не пытайся сразу построить "идеальную систему".

Для filmoteka важнее:
- устойчивый импорт,
- понятная доменная модель,
- рабочий локальный просмотр,
- предсказуемое развитие проекта.

Сначала простая, прочная основа. Потом усложнение.
