# docs/architecture-decisions.md

# Filmoteka — Architecture Decisions Log

> Это журнал архитектурных решений проекта filmoteka.
>
> Правила ведения:
> - Одна запись = одно архитектурное решение.
> - Не редактировать старые `accepted` записи по смыслу.
> - Если решение изменилось, создать новую запись со статусом `superseded` или `accepted`, сослаться на старую и объяснить, что поменялось.
> - Фиксировать не все подряд, а только значимые решения:
>   - влияющие на структуру системы,
>   - влияющие на важные нефункциональные свойства,
>   - дорогие для отката,
>   - вызывающие заметные trade-offs.
> - Запись должна быть короткой, но достаточной, чтобы через месяцы было понятно: **почему мы так сделали**. [web:274][web:278]

---

## Status values

- `proposed` — предложено, но ещё не зафиксировано окончательно
- `accepted` — принято как текущее рабочее решение
- `superseded` — заменено более новым решением
- `rejected` — рассмотрено и отвергнуто
- `deprecated` — решение устарело, но пока ещё живо в системе

---

## ADR Index

| ID | Title | Status | Date |
|---|---|---|---|
| ADR-001 | Modular monolith as initial architecture | accepted | 2026-06-03 |
| ADR-002 | Python as primary backend language | accepted | 2026-06-03 |
| ADR-003 | FastAPI as HTTP API framework | accepted | 2026-06-03 |
| ADR-004 | PostgreSQL as primary database | accepted | 2026-06-03 |
| ADR-005 | Redis-backed background jobs | accepted | 2026-06-03 |
| ADR-006 | Docker Compose as local deployment model | accepted | 2026-06-03 |
| ADR-007 | src layout for repository structure | accepted | 2026-06-03 |
| ADR-008 | YAML spec for library paths and rules | accepted | 2026-06-03 |
| ADR-009 | Secrets live in `.env`, not in spec | accepted | 2026-06-03 |
| ADR-010 | Separate movie, edition, and media file entities | accepted | 2026-06-03 |
| ADR-011 | Idempotent import as a hard requirement | accepted | 2026-06-03 |
| ADR-012 | Metadata enrichment must degrade gracefully offline | accepted | 2026-06-03 |
| ADR-013 | Keep project instructions in `AGENTS.md` | accepted | 2026-06-03 |
| ADR-014 | Separate unit, integration, and e2e tests | accepted | 2026-06-03 |
| ADR-015 | Import pipeline — wired end-to-end, bridge step, admin trigger | accepted | 2026-06-07 |
| ADR-016 | OMDB replaces TMDb as poster source | accepted | 2026-06-10 |
| ADR-017 | Scan-only import (no copy/move) | accepted | 2026-06-10 |
| ADR-018 | Caddy reverse proxy + public health endpoint | accepted | 2026-06-10 |
| ADR-019 | TV Series as separate entity | accepted | 2026-06-17 |
| ADR-020 | Multi-step poster search with type detection | accepted | 2026-06-17 |
| ADR-021 | In-memory progress dict for batch operations | accepted | 2026-06-17 |
| ADR-022 | PostgreSQL full-text search replacing ILIKE | accepted | 2026-06-17 |
| ADR-023 | Remove ffmpeg remux (superseded by transcode pipeline) | accepted | 2026-06-17 |

---

# ADR Template

> Копируй этот блок для новой записи.

## ADR-XXX: <title>

- Status: `proposed | accepted | superseded | rejected | deprecated`
- Date: `YYYY-MM-DD`
- Deciders:
  - ...
  - ...
- Related:
  - PRD section: ...
  - Tasklist items: ...
  - Supersedes: ...
  - Superseded by: ...

### Context
Что за проблема, ограничение или развилка привели к необходимости решения:
- ...
- ...
- ...

### Decision
Что именно выбрано:
- ...
- ...
- ...

### Options considered
1. Option A
   - Pros:
     - ...
   - Cons:
     - ...
2. Option B
   - Pros:
     - ...
   - Cons:
     - ...

### Consequences
Что это решение нам даёт и чем мы за него платим:
- Positive:
  - ...
- Negative:
  - ...
- Neutral / follow-up:
  - ...

### Notes
Дополнительные замечания:
- ...
- ...

---

# Accepted Decisions

## ADR-019: TV Series as separate entity

- Status: `accepted`
- Date: `2026-06-17`
- Deciders: mrsalt3000
- Related:
  - Tasklist items: SERIES-001, SERIES-002, SERIES-003, SERIES-004
  - Supersedes: (none — new feature)

### Context

90 из 164 фильмов в библиотеке — эпизоды 5 сериалов (Gravity Falls,
The Mandalorian, Andor, Ahsoka, Obi Wan Kenobi). Каждый эпизод хранится
как отдельный Film с названием вида "Gravity Falls S01E01 IVI SOFCJ".
На главной странице каталога все 164 элемента показываются как
отдельные карточки.

### Decision

Создать отдельную сущность `Series` с собственным ID, названием,
постером. На `Film` добавить поля `series_id` (FK → series.id),
`season_number`, `episode_number`, `episode_title`. Во время импорта
(filename_parser → _bridge_to_catalog) эпизоды автоматически
группируются в Series.

### Options considered

1. **Отдельная таблица Series + поля на Film** ← выбрано
   - Прозрачная модель, простой API, FK integrity
2. **Группировка через теги/категории** — сложнее поддерживать,
   нет FK integrity
3. **Только текстовое поле series_name на Film** — не масштабируется,
   сложно для API

### Consequences

- Positive: одна карточка на сериал на главной, навигация по сезонам,
  prev/next в плеере
- Negative: импорт требует find-or-create Series, ++сложность
  filename_parser


## ADR-020: Multi-step poster search with type detection

- Status: `accepted`
- Date: `2026-06-17`
- Deciders: mrsalt3000
- Related:
  - Tasklist items: POSTER-001, POSTER-002, POSTER-003

### Context

OMDB API ищет постер по названию, но многие поиски не дают результата
из-за технических маркеров в названии (HDTVRip, WEB-DL, 1080p, RUS, DUB),
неправильного типа (movie vs series) и отсутствия IMDb ID.

### Decision

Реализовать 3-шаговый поиск:
1. **Clean title**: удалить технические маркеры из названия перед поиском
2. **Type detection**: определить movie/series по эвристикам (season/episode
   keywords) и году
3. **IMDb ID fallback**: если title+year не дал результата — использовать
   DeepSeek-структурированный запрос для получения IMDb ID, затем поиск
   по `?i=imdbID`

### Options considered

1. **Одношаговый `?t=title&y=year`** — базовый, не находит много постеров
2. **Многошаговый с type + IMDb ID** ← выбрано
3. **Поиск через несколько API (OMDB + TMDb)** — избыточно, OMDB достаточно

### Consequences

- Positive: значительно больше постеров находится, особенно для сериалов
- Negative: увеличение времени поиска (3 запроса вместо 1), зависимость
  от DeepSeek для IMDb ID


## ADR-021: In-memory progress dict for batch operations

- Status: `accepted`
- Date: `2026-06-17`
- Deciders: mrsalt3000
- Related:
  - Tasklist items: POSTER-004, V3-004, BUGFIX-017

### Context

Фоновые batch-операции (алиасы, постеры, enrichment, транскодинг)
длятся минуты. Пользователь видит только финальный summary. Невозможно
отследить, какие файлы обрабатываются и какие упали с ошибкой.

### Decision

Хранить per-item прогресс в in-memory dict (module-level), ключ — job_id.
Структура: `dict[int, list[FileStatus]]`, где `FileStatus` — dataclass
с полями (id, name, status, error). Endpoint `GET /admin/{op}-progress/{id}`
отдаёт текущее состояние. Фронтенд polling каждые 2 секунды.

### Options considered

1. **In-memory dict** ← выбрано — простота, не требует БД/Redis,
   достаточно для одного admin-пользователя
2. **Progress в БД (background_jobs.result)** — сложнее, запись на
   каждый элемент дорого
3. **Redis pub/sub** — избыточно для текущих потребностей

### Consequences

- Positive: live-таблицы, простой код, переиспользуемый паттерн
- Negative: прогресс теряется при рестарте API, только для одного
  admin-пользователя


## ADR-022: PostgreSQL full-text search replacing ILIKE

- Status: `accepted`
- Date: `2026-06-17`
- Deciders: mrsalt3000
- Related:
  - Tasklist items: V1-008

### Context

Поиск по каталогу использовал `ILIKE '%q%'` с пятикратным OR через
Film.title, Film.description, Genre.name, Person.name, MediaFile.media_alias.
`ILIKE` не использует индексы при `%q%`, медленный на больших данных,
не ранжирует результаты.

### Decision

Добавить колонку `fts_vector` (TSVECTOR) + GIN-индекс на films.
Вектор включает title, description, episode_title, genre names,
person names. При поиске `?q=...` используем
`fts_vector @@ plainto_tsquery('russian', q)` и ранжируем по
`ts_rank DESC`. Функция `_update_fts_vector()` обновляет вектор
после импорта, enrichment и admin-редактирования.

### Options considered

1. **ILIKE (status quo)** — просто, но не масштабируется
2. **`fts_vector` + GIN** ← выбрано — нативная PostgreSQL FTS,
   русский стемминг, ранжирование
3. **Elasticsearch** — избыточно для локального архива

### Consequences

- Positive: релевантное ранжирование, русский стемминг, быстрый поиск
- Negative: нужно обновлять `fts_vector` при изменении данных,
  миграция для существующих данных


## ADR-023: Remove ffmpeg remux (superseded by transcode pipeline)

- Status: `accepted`
- Date: `2026-06-17`
- Deciders: mrsalt3000
- Related:
  - Tasklist items: BUGFIX-009, BUGFIX-027
  - Supersedes: (the old ffmpeg pipe approach from V1)

### Context

BUGFIX-009 заменил on-the-fly ffmpeg pipe для MKV (fragmented MP4
с `empty_moov`/`delay_moov`) на двухшаговый транскодинг:
AC3→AAC → MKV→MP4 с `+faststart`. После транскодирования `.tr.mp4`
is served via FileResponse с полноценной поддержкой Range-запросов.
Ремукс-код в `media.py` стал dead code — он не вызывается, если
все файлы прошли транскодирование.

### Decision

Удалить `_ffmpeg_remux_stream()`, `_ffmpeg_available()`, MKV-415 guard,
MKV probe+remux block из `stream_media()`. MKV без `.tr.mp4` теперь
передаётся через FileResponse — браузер сам решает, может ли его
воспроизвести.

### Options considered

1. **Оставить dead code** — запутывает код, ложные ожидания
2. **Удалить** ← выбрано — чистота кода, понятное поведение
3. **Переписать на новый ffmpeg pipe** — не нужно, транскодинг
   решает проблему

### Consequences

- Positive: -125 строк мёртвого кода, проще `stream_media()`
- Negative: файлы MKV без `.tr.mp4` не открываются в браузерах
  без поддержки контейнера (Edge поддерживает, Chrome/Firefox нет)


## ADR-001: Modular monolith as initial architecture

- Status: `accepted`
- Date: `2026-06-03`
- Deciders:
  - project owner
  - coding agent
- Related:
  - PRD section: core architecture
  - Tasklist items: INIT-001, INIT-005, MVP-001

### Context
Проект filmoteka на старте содержит сразу несколько важных доменов:
- импорт локальной медиатеки,
- каталог,
- метаданные,
- воспроизведение,
- история просмотров,
- профили пользователей,
- рекомендации,
- админские сценарии.

При этом проект стартует как домашняя система с ограниченной командой разработки и без необходимости раннего горизонтального масштабирования.

### Decision
На старте используется **модульный монолит**:
- один backend application,
- одна основная база данных,
- отдельный worker для фоновых задач,
- но без распила на независимые микросервисы.

Код делится по доменам внутри одного репозитория и одного deployable backend.

### Options considered
1. Modular monolith
   - Pros:
     - проще стартовать
     - проще дебажить
     - меньше инфраструктурной сложности
     - легче поддерживать согласованность модели данных
   - Cons:
     - при росте системы потребуется дисциплина модульных границ
     - возможен риск "god app", если не следить за структурой

2. Microservices from day one
   - Pros:
     - можно жёстко разделить bounded contexts
     - потенциально легче масштабировать по частям
   - Cons:
     - резко усложняет локальную разработку
     - требует сложной оркестрации и контрактов
     - создаёт ненужную сложность для early-stage проекта

### Consequences
- Positive:
  - низкий порог старта
  - единая доменная модель
  - меньше operational overhead
- Negative:
  - нужно внимательно следить за boundaries между модулями
- Neutral / follow-up:
  - при росте можно выделить части в отдельные сервисы позже

### Notes
Модульный монолит здесь — сознательный выбор в пользу скорости и управляемости, а не компромисс "потому что так проще".

---

## ADR-002: Python as primary backend language

- Status: `accepted`
- Date: `2026-06-03`
- Deciders:
  - project owner
  - coding agent
- Related:
  - PRD section: platform independence
  - Tasklist items: INIT-004, INIT-005

### Context
Проект должен быть платформенно независимым, запускаться в Docker Compose, иметь удобный стек для API, импорта файлов, интеграций с LLM и metadata providers.

### Decision
Основной backend язык — **Python**.

### Options considered
1. Python
   - Pros:
     - удобен для файловых пайплайнов
     - удобен для API и фоновых задач
     - хорошо подходит для LLM и enrichment-интеграций
   - Cons:
     - не лучший выбор для CPU-heavy media processing

2. Go
   - Pros:
     - выше производительность
     - удобные статические бинарники
   - Cons:
     - больше трения для LLM и data-enrichment сценариев
     - медленнее старт доменной разработки

3. Node.js
   - Pros:
     - единый язык с frontend
   - Cons:
     - менее удобен для части backend/data tooling задач проекта

### Consequences
- Positive:
  - быстрый старт
  - хорошая экосистема для FastAPI, SQLAlchemy, workers, parsing, metadata enrichment
- Negative:
  - критичные CPU-intensive сценарии могут потребовать выноса в отдельные утилиты
- Neutral / follow-up:
  - media probing может использовать внешние CLI-инструменты

---

## ADR-003: FastAPI as HTTP API framework

- Status: `accepted`
- Date: `2026-06-03`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: INIT-006, MVP-016

### Context
Нужен современный HTTP framework для:
- API каталога,
- auth,
- admin endpoints,
- playback endpoints,
- integration-friendly development.

### Decision
Основной HTTP framework — **FastAPI**.

### Options considered
1. FastAPI
   - Pros:
     - высокая скорость разработки
     - хорошие типы и валидация
     - удобен для API-first сценария
   - Cons:
     - нужно следить, чтобы бизнес-логика не утекала в route handlers

2. Django
   - Pros:
     - батарейки в комплекте
   - Cons:
     - тяжелее для выбранной модульной структуры
     - часть возможностей будет избыточной

3. Flask
   - Pros:
     - минимализм
   - Cons:
     - больше ручной инфраструктуры вокруг

### Consequences
- Positive:
  - быстрый API bootstrap
  - удобная схема request/response validation
- Negative:
  - дисциплина архитектуры важнее, иначе получатся "толстые роуты"
- Neutral / follow-up:
  - доменная логика живёт вне API-слоя

---

## ADR-004: PostgreSQL as primary database

- Status: `accepted`
- Date: `2026-06-03`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: MVP-001, MVP-002, V1-008

### Context
Нужно хранить:
- карточки фильмов,
- версии и файлы,
- историю просмотров,
- прогресс просмотра,
- метаданные,
- фоновые задачи,
- пользовательские ограничения,
- рекомендации.

Также нужен полнотекстовый поиск и строгие ограничения целостности.

### Decision
Основная БД — **PostgreSQL**.

### Options considered
1. PostgreSQL
   - Pros:
     - strong relational model
     - FTS
     - ограничения целостности
     - зрелость и надёжность
   - Cons:
     - требует отдельного контейнера и миграций

2. SQLite
   - Pros:
     - проще старт
   - Cons:
     - ограничен для concurrency, FTS-сценариев и growth path

3. MongoDB
   - Pros:
     - гибкие документы
   - Cons:
     - хуже подходит для строгих связей и транзакционного ядра проекта

### Consequences
- Positive:
  - хорошая база под каталог, поиск и историю
  - удобно поддерживать сложные связи
- Negative:
  - нужен disciplined migration workflow
- Neutral / follow-up:
  - search и recommendation read models можно оптимизировать позже

---

## ADR-005: Redis-backed background jobs

- Status: `accepted`
- Date: `2026-06-03`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: V1-023, V1-024

### Context
Импорт, enrichment, постеры, внешние ссылки, переиндексация и рекомендации не должны блокировать HTTP API.

### Decision
Фоновые задачи выполняются через **worker + Redis-backed queue**.

### Options considered
1. Redis + worker
   - Pros:
     - простой и понятный operational model
     - хорошо подходит для Compose-окружения
   - Cons:
     - добавляет инфраструктурный компонент

2. Только background tasks внутри web process
   - Pros:
     - меньше компонентов
   - Cons:
     - риск блокировки API
     - плохо управляется при росте задач

3. Полноценный message broker с более тяжёлым стеком
   - Pros:
     - гибкость
   - Cons:
     - слишком сложно для старта

### Consequences
- Positive:
  - тяжёлые задачи уходят из request path
  - проще retry/recovery model
- Negative:
  - нужно мониторить queue и worker state
- Neutral / follow-up:
  - later можно усилить job orchestration при необходимости

---

## ADR-006: Docker Compose as local deployment model

- Status: `accepted`
- Date: `2026-06-03`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: INIT-007, INIT-010

### Context
Проект должен запускаться локально и в домашней сети, быть платформенно независимым и простым для разработки.

### Decision
Основной deployment model на старте — **Docker Compose**.

### Options considered
1. Docker Compose
   - Pros:
     - простой локальный orchestration
     - удобно для db + redis + api + worker + proxy
   - Cons:
     - ограничен для production-grade distributed deployment

2. Запуск всего руками без контейнеров
   - Pros:
     - меньше контейнерной обвязки
   - Cons:
     - хуже воспроизводимость окружения

3. Kubernetes
   - Pros:
     - высокий ceiling
   - Cons:
     - радикально избыточно для старта

### Consequences
- Positive:
  - воспроизводимый локальный запуск
  - легко поднимать весь стек одной командой
- Negative:
  - позже возможна отдельная история деплоя вне Compose
- Neutral / follow-up:
  - compose остаётся базовым dev/home deployment инструментом

---

## ADR-007: src layout for repository structure

- Status: `accepted`
- Date: `2026-06-03`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: INIT-001, INIT-005

### Context
Нужна масштабируемая структура Python-проекта, отделяющая исходный код от конфигов, тестов и скриптов.

### Decision
Используется **src layout**:
- `src/filmoteka/`
- `tests/`
- `docker/`
- `specs/`
- `docs/`

### Options considered
1. src layout
   - Pros:
     - чище импорты
     - понятнее packaging model
     - легче масштабировать
   - Cons:
     - чуть сложнее начальная настройка

2. Flat layout
   - Pros:
     - быстрее начать
   - Cons:
     - больше риска запутанных импортов и разрастания корня

### Consequences
- Positive:
  - чистая структура
  - лучшее разделение concerns
- Negative:
  - нужно сразу правильно настроить tooling
- Neutral / follow-up:
  - доменные подпапки проектируются отдельно

---

## ADR-008: YAML spec for library paths and rules

- Status: `accepted`
- Date: `2026-06-03`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: INIT-012, MVP-008

### Context
В проекте есть бизнес-конфиг, который описывает:
- пути к папкам,
- правила раскладки,
- параметры импорта,
- пользовательские ограничения по библиотеке.

Эти данные не являются секретами и должны быть легко редактируемыми.

### Decision
Product/library configuration хранится в **`specs/library.yaml`**.

### Options considered
1. YAML spec
   - Pros:
     - удобно читать и править руками
     - хорошо подходит для декларативных правил
   - Cons:
     - нужна валидация структуры

2. Хранить всё в `.env`
   - Pros:
     - меньше файлов
   - Cons:
     - плохо подходит для сложного структурированного конфига

3. Хранить всё в БД с первого дня
   - Pros:
     - централизованно
   - Cons:
     - сложнее старт, bootstrap paradox

### Consequences
- Positive:
  - понятный, редактируемый business config
- Negative:
  - нужно поддерживать schema validation
- Neutral / follow-up:
  - позже часть правил может переехать в admin UI

---

## ADR-009: Secrets live in `.env`, not in spec

- Status: `accepted`
- Date: `2026-06-03`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: INIT-002, INIT-011

### Context
Проект использует внешние интеграции и внутренние сервисные настройки, где есть секреты и чувствительные значения.

### Decision
Секреты и environment-specific значения хранятся в **`.env`**, а не в `specs/library.yaml`.

### Options considered
1. `.env` for secrets, YAML for business rules
   - Pros:
     - чистое разделение ответственности
     - проще ротация секретов
   - Cons:
     - два источника конфигурации вместо одного

2. Всё в одном YAML
   - Pros:
     - один файл
   - Cons:
     - плохое разделение секрета и бизнес-логики

### Consequences
- Positive:
  - безопаснее и чище
- Negative:
  - нужен понятный docs/runbook
- Neutral / follow-up:
  - обязательный `.env.example`

---

## ADR-010: Separate movie, edition, and media file entities

- Status: `accepted`
- Date: `2026-06-03`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: MVP-002, V2-009

### Context
Один и тот же фильм может существовать:
- в нескольких качествах,
- в нескольких переводах,
- в режиссёрской версии,
- в нескольких файлах.

Если хранить всё как одну сущность, импорт и дедупликация быстро становятся неуправляемыми.

### Decision
Разделить модель на:
- `movie`
- `movie_edition`
- `media_file`

### Options considered
1. Separate entities
   - Pros:
     - корректная модель предметной области
     - удобнее дедупликация и конфликты
   - Cons:
     - сложнее схема БД и API

2. Single movie table with file fields
   - Pros:
     - проще стартовая реализация
   - Cons:
     - очень быстро ломается на реальных данных

### Consequences
- Positive:
  - архитектурная база под качественный импорт
- Negative:
  - больше таблиц и связей
- Neutral / follow-up:
  - UI должен уметь объяснять пользователю версии фильма

---

## ADR-011: Idempotent import as a hard requirement

- Status: `accepted`
- Date: `2026-06-03`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: MVP-014, V2-009

### Context
Импорт будет запускаться многократно на тех же папках. Повторный запуск не должен ломать библиотеку и плодить дубли.

### Decision
Идемпотентность импорта считается **жёстким инвариантом системы**.

### Options considered
1. Idempotent import
   - Pros:
     - безопасный повторный запуск
     - меньше ручной чистки
   - Cons:
     - нужна более сложная логика сопоставления

2. "Best effort" import without strong guarantees
   - Pros:
     - быстрее реализовать
   - Cons:
     - быстро превращает библиотеку в мусор

### Consequences
- Positive:
  - устойчивость эксплуатации
- Negative:
  - import pipeline нужно проектировать аккуратно с самого начала
- Neutral / follow-up:
  - тесты на повторный импорт обязательны

---

## ADR-012: Metadata enrichment must degrade gracefully offline

- Status: `accepted`
- Date: `2026-06-03`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: V2-013, V2-014, V2-015

### Context
Локальная библиотека должна быть usable даже без интернета, недоступности LLM или проблем внешних metadata providers.

### Decision
Enrichment и recommendations, зависящие от внешних сервисов, должны **деградировать мягко**, а каталог и просмотр — продолжать работать.

### Options considered
1. Graceful degradation
   - Pros:
     - библиотека остаётся полезной офлайн
     - меньше operational fragility
   - Cons:
     - нужно отдельно продумывать fallback paths

2. Hard dependency on external services
   - Pros:
     - проще единый flow
   - Cons:
     - ломает главный смысл локальной системы

### Consequences
- Positive:
  - core product value сохраняется офлайн
- Negative:
  - статусы enrichment задач становятся сложнее
- Neutral / follow-up:
  - нужны retry/pending/deferred states

---

## ADR-013: Keep project instructions in `AGENTS.md`

- Status: `accepted`
- Date: `2026-06-03`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: INIT-002, INIT-013

### Context
Проект разрабатывается с участием coding agent. Нужно единое место, где лежат project instructions для агента.

### Decision
Рабочие инструкции для агента хранятся в **`AGENTS.md`** и подключаются как project context file.

### Options considered
1. `AGENTS.md`
   - Pros:
     - удобно для агента и человека
     - прозрачно лежит в репозитории
   - Cons:
     - требует дисциплины обновления

2. Размазанные инструкции по разным doc-файлам
   - Pros:
     - можно писать где удобно
   - Cons:
     - агенту сложнее работать последовательно

### Consequences
- Positive:
  - единый operational source of truth для агента
- Negative:
  - нужно следить за актуальностью файла
- Neutral / follow-up:
  - tasklist и progress log дополняют `AGENTS.md`

---

## ADR-014: Separate unit, integration, and e2e tests

- Status: `accepted`
- Date: `2026-06-03`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: INIT-014, MVP-015, V2-026

### Context
Проект включает:
- доменную логику,
- БД,
- файловую систему,
- HTTP API,
- браузерный UI,
- фоновые задачи.

Один тип тестов не сможет адекватно покрыть всё.

### Decision
Тесты разделяются на:
- `tests/unit`
- `tests/integration`
- `tests/e2e`

### Options considered
1. Separate layers of tests
   - Pros:
     - понятнее скорость и глубина проверки
     - удобнее запускать нужный набор
   - Cons:
     - требуется дисциплина в выборе уровня теста

2. Смешанный набор тестов без чёткого деления
   - Pros:
     - проще быстро начать
   - Cons:
     - тестовый контур быстро становится непрозрачным

### Consequences
- Positive:
  - тестовая стратегия более предсказуема
  - агенту проще выбирать подходящий уровень проверки
- Negative:
  - нужно следить, чтобы integration/e2e не заменяли unit tests
- Neutral / follow-up:
  - обязательен тестовый runbook

---

## ADR-015: Import pipeline — wired end-to-end, bridge step, admin trigger

- Status: `accepted`
- Date: `2026-06-07`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: V1-001

### Context
MVP реализовал отдельные доменные функции импорта (scan → probe → layout) и каталога (Film, MovieEdition, MediaFile), но:
- `scan_downloads()`, `probe_candidates()`, `layout_file()` ниоткуда не вызывались
- не было bridge-шага ImportCandidate → Film/MovieEdition/MediaFile
- `load_library_config()` не вызывалась — YAML-конфиг не использовался
- не было API для триггера импорта
- пути из `.env` (`DOWNLOADS_ROOT`, `LIBRARY_ROOT`) не читались

### Decision
Собрать сквозной импортный пайплайн:
1. `Settings` читает `downloads_root`/`library_root` из `.env` (опционально, переопределяют `library.yaml`)
2. `app.py` lifespan загружает `LibraryConfig` при старте
3. `pipeline.py` — `run_import()` последовательно вызывает scan → probe → layout → bridge
4. Bridge создаёт Film (dedup по title+year), MovieEdition (dedup по film_id+quality), MediaFile
5. `POST /admin/import/scan` — защищённый endpoint для ручного запуска

### Options considered
1. **Single orchestrator with bridge** (выбрано)
   - Pros:
     - единая точка входа для всего пайплайна
     - понятный flow
     - easy to test end-to-end
   - Cons:
     - synchronous — не подходит для больших библиотек (будет выделено в background job в V1-023)

2. **Раздельные admin endpoints** (scan / probe / layout / bridge по отдельности)
   - Pros:
     - максимальная гибкость
   - Cons:
     - нужна координация между вызовами
     - больше API поверхности
     - сложнее idempotency

3. **Автоимпорт при старте**
   - Pros:
     - zero-touch
   - Cons:
     - блокирует старт при большой библиотеке
     - нет контроля у пользователя
   - (Отложено — можно сделать опционально позже)

### Consequences
- Positive:
  - библиотека перестаёт быть пустой после вызова импорта
  - понятный API для админа
  - пути конфигурируются через `.env` для Windows/Linux
- Negative:
  - синхронный пайплайн — для большого количества файлов нужно выделять в background
  - bridge-дедупликация простая (title+year) — для разных версий/качеств одного фильма нужна будет доработка в V2
- Neutral / follow-up:
  - V1-023: background jobs для импорта
  - V2-009: advanced dedup

---

## ADR-016: OMDB replaces TMDb as poster source

- Status: `accepted`
- Date: `2026-06-10`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: V1-039

### Context
Исходный проект использовал TMDb API для поиска постеров и Kinopoisk
для внешних ссылок. TMDb API — бесплатный, но требует регистрации
и имеет лимиты. Kinopoisk API нестабилен и часто меняет условия.

### Decision
Заменить TMDb и Kinopoisk на **OMDB** как единственный источник
постеров. OMDB предоставляет:
- поиск по названию + году (`?t=...&y=...`),
- fuzzy fallback через `?s=...`
- достаточное покрытие для домашней библиотеки.

`TMDB_API_KEY` → `OMDB_API_KEY` в настройках. `Film.kinopoisk_url`
удалён из модели. Весь старый TMDb-код удалён.

### Options considered
1. **OMDB** (выбрано)
   - Pros: простой API, бесплатный ключ, достаточное покрытие
   - Cons: нет трейлеров, нет актёров/описания (только постеры)
2. **Оставить TMDb**
   - Pros: богаче данные (actors, description)
   - Cons: Kinopoisk ссылки не работают, два API вместо одного

### Consequences
- Positive: один провайдер, проще код, меньше ключей
- Negative: только постеры, без дополнительных метаданных
- Follow-up: метаданные (жанры, описание) остаются на уровне filename parse

---

## ADR-017: Scan-only import (no copy/move)

- Status: `accepted`
- Date: `2026-06-10`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: V1-029

### Context
Исходный импорт предполагал копирование/перемещение файлов из
`downloads_root` в `library_root`. На практике пользователь хранит
файлы сразу в финальной папке. Копирование — лишняя операция,
которая занимает место и время.

### Decision
Импорт **только индексирует** файлы в `LIBRARY_ROOT`. Файлы не
копируются и не перемещаются. `downloads_root` и layout-шаг удалены.
`LIBRARY_ROOT` — единственная директория, с которой работает импорт.

### Options considered
1. **Scan-only** (выбрано)
   - Pros: быстро, идемпотентно, не занимает место
   - Cons: нет сортировки по папкам
2. Copy/move из downloads
   - Pros: чистая библиотека с сортировкой
   - Cons: медленно, требует места, сложнее идемпотентность
3. Optional layout
   - Pros: гибкость
   - Cons: сложнее код, редко используется

### Consequences
- Positive: простой и быстрый импорт
- Negative: организация папок остаётся на пользователе
- Follow-up: можно добавить опциональный layout позже

---

## ADR-018: Caddy reverse proxy + public health endpoint

- Status: `accepted`
- Date: `2026-06-10`
- Deciders:
  - project owner
  - coding agent
- Related:
  - Tasklist items: V2-013, V2-021, V2-022, V2-023

### Context
Проект вырос из одного API-сервиса в стек: API, worker, frontend.
Пользователь открывает браузер и ожидает единую точку входа.
Нужен reverse proxy и health check для мониторинга.

### Decision
- **Caddy 2** как reverse proxy (замена nginx, который был на старте)
- Caddy обслуживает frontend (SPA) и проксирует `/api/` → FastAPI
- Публичный `GET /health` проверяет БД и внешние сервисы,
  не требует аутентификации
- Frontend показывает offline-баннер при недоступности API

### Options considered
1. **Caddy** (выбрано)
   - Pros: автоматические HTTPS, простой Caddyfile, встроенная
     поддержка SPA (try_files)
   - Cons: ещё один компонент в стеке
2. **Nginx** (был изначально)
   - Pros: привычный, зрелый
   - Cons: нет авто-HTTPS, сложнее настройка SPA fallback

### Consequences
- Positive: единый порт для пользователя, автоматический HTTPS
- Negative: дополнительный контейнер
- Follow-up: для home-сети достаточно HTTP (Caddy настроен на порт 80)

---

# Future Decisions Backlog

> Сюда заносить темы, которые почти наверняка потребуют отдельного ADR позже.

- Recommendation engine architecture
- Choice of background job library
- Media streaming strategy for large files
- Poster storage strategy
- Full-text search schema evolution
- Admin conflict-resolution UX
- Backup retention policy
- Home-network publishing and access control
- Observability stack
- Family video storage and privacy model

---

# Change Log Policy

Если решение меняется:
1. Не переписывать старый `accepted` ADR.
2. Создать новый ADR.
3. У старого поставить `superseded`, если это уместно.
4. Связать записи через поля:
   - `Supersedes`
   - `Superseded by`

Это сохраняет историю мышления команды и агента.
