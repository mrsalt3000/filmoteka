# Filmoteka

Домашний видео хостинг над локальным киноархивом.

Хранит, каталогизирует и воспроизводит локальную медиатеку через браузер.
Поддерживает детские профили, семейное видео, персональные рекомендации,
offline-режим и фоновые операции (импорт, обогащение метаданных, backup).

## Stack

- **Backend:** Python 3.11+ / FastAPI / SQLAlchemy 2.0 / Alembic
- **Database:** PostgreSQL 16
- **Queue:** Redis 7
- **Proxy:** Caddy 2 (автоматические HTTPS, единая точка входа)
- **Deployment:** Docker Compose
- **Frontend:** vanilla JS SPA (без фреймворка)

## Quick start

```bash
# 1. Клонировать репозиторий
git clone https://github.com/mrsalt3000/filmoteka.git
cd filmoteka

# 2. Настроить окружение
cp .env.example .env
# Отредактировать .env — см. раздел "Configuration"

# 3. Запустить стек
docker compose up --build
```

После запуска:
- **Frontend:** http://localhost (Caddy, порт 80)
- **API:** http://localhost:8000 (прямой доступ)
- **Admin:** логин `mrsalt3000` / `dev` (если включён seed)

## Configuration

### `.env`

| Переменная | Обязательная | Описание |
|---|---|---|
| `DATABASE_URL` | да | PostgreSQL connection string |
| `REDIS_URL` | да | Redis connection string |
| `SECRET_KEY` | да | Секретный ключ для JWT (минимум 32 символа) |
| `LIBRARY_ROOT` | да | Путь к папке с медиафайлами |
| `OMDB_API_KEY` | нет | API-ключ OMDB для постеров (http://omdbapi.com) |
| `BACKUP_DIR` | нет | Директория для backup-файлов (по умолч. `/backups`) |
| `HTTP_PROXY` | нет | HTTP proxy для исходящих запросов |
| `HTTPS_PROXY` | нет | HTTPS proxy для исходящих запросов |

Пример:

```ini
DATABASE_URL=postgresql+psycopg://filmoteka:filmoteka@localhost:5432/filmoteka
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-32-char-random-secret-here
LIBRARY_ROOT=D:/Filmoteka
OMDB_API_KEY=your-omdb-key
```

### `specs/library.yaml`

Бизнес-правила библиотеки: расширения файлов для импорта, максимальный
размер файла, схема организации папок. Секреты в этот файл не класть.

## Usage

### Импорт библиотеки

После первого запуска библиотека пуста. Импорт запускается вручную:

```bash
# Через admin API (требуется admin-токен)
curl -X POST http://localhost:8000/admin/import/scan \
  -H "Authorization: Bearer <token>"
```

Импорт **только индексирует** файлы в `LIBRARY_ROOT` — ничего не копирует
и не перемещает. Каждый файл становится `MediaFile` внутри `MovieEdition → Film`.
Файлы группируются по названию и году.

Повторный запуск идемпотентен — дубли не создаются.

**Поддерживаемые расширения:** `.mp4`, `.mkv`, `.avi`, `.mov`, `.m4v`, `.ts`.

### Каталог

- `GET /films` — список фильмов с пагинацией, фильтрацией и поиском
- `GET /films/{id}` — карточка фильма (описание, жанры, актёры, версии, файлы)
- `GET /films?q=...` — поиск по названию, описанию, жанрам, актёрам
- `GET /films?genre=...&year_from=...&year_to=...` — фильтры
- `GET /films?is_family_video=true` — семейное видео
- `GET /films?include_family=true` — показать семейное видео в общей выдаче

### Просмотр

- `POST /media/{id}/watch/start` — начать просмотр, получить `watch_event_id`
- `PATCH /media/{id}/watch/{event_id}/progress` — сохранить прогресс (`{"position": 120.5}`)
- `GET /media/{id}/watch/state` — получить состояние (для resume)
- `GET /media/watch/history` — история просмотров

Плеер доступен во фронтенде по `#play/{mediaId}`.

**Поддержка MKV:** при наличии ffmpeg в PATH — ремукс в MP4 на лету
(copy-операция, без перекодирования). Без ffmpeg возвращается 415.

### Рекомендации

- `GET /me/recommendations` — персональные рекомендации на основе истории
- `POST /me/recommendations/by-mood` — рекомендации по настроению
  (LLM + keyword fallback, `LLM_API_URL` в `.env`)
- `GET /admin/recommendations/download` — "что скачать" (админ)

Тумблеры (влияют на рекомендации и каталог):
- exclude-watched, include-external, filter-by-language, exclude-family

### Профили

- `POST /admin/users` — создать пользователя (admin/child)
- `PUT /me/incognito` — инкогнито (просмотры не сохраняются)
- `DELETE /me/watch/history` — очистить историю
- `POST /me/blacklist/{film_id}` — скрыть фильм из выдачи

Child-аккаунты: возрастная группа `age_group` (0_6, 7_12, 13_17),
фильтруется по `age_rating` на фильмах.

### Admin

Все admin-эндпоинты доступны только с ролью `admin`:
- `POST /admin/import/scan` — запустить импорт (фоновый job, 202)
- `POST /admin/posters/fill-missing` — заполнить отсутствующие постеры
- `POST /admin/posters/refresh-all` — обновить все постеры
- `GET /admin/conflicts` — конфликты дедупликации
- `PATCH /admin/conflicts/{id}/resolve` — разрешить конфликт
- `POST /admin/media/reindex` — переиндексация путей
- `POST /admin/backup` — backup БД (pg_dump)
- `GET /admin/backups` — список backup-файлов
- `POST /admin/restore/{filename}` — восстановить из backup
- `GET /admin/jobs` / `GET /admin/jobs/{id}` — статусы фоновых задач
- `GET /admin/watch-stats` — статистика просмотров

### Health check

```bash
GET /health
# → {"status":"ok","database":{"status":"ok"},"external":{"status":"ok"},"version":"2.0.0"}
```

Публичный эндпоинт, не требует аутентификации.

### Frontend (SPA)

Одностраничное приложение на vanilla JS. Доступно по `http://localhost/`.

- `#list` — каталог фильмов (сетка)
- `#film/{id}` — карточка фильма
- `#play/{mediaId}` — плеер
- `#admin` — админ-панель (логин/logout, кнопки импорта, постеров, backup)
- Тёмная/светлая тема — переключение в навбаре
- Offline-баннер при недоступности API

## Project layout

```
src/filmoteka/          — backend source
  api/                  — HTTP route handlers
  domain/               — domain logic (catalog, importing, watching, access)
  infrastructure/       — db, config, logging, metadata providers
  tasks/                — background jobs
tests/
  unit/                 — unit tests (144)
  integration/          — integration tests (214+)
  e2e/                  — e2e tests (5)
docker/                 — Dockerfiles (api, worker), Caddyfile
specs/                  — business config (library.yaml)
migrations/             — Alembic migrations (18)
scripts/                — run-all-checks.sh, run-coverage.sh
docs/                   — project docs
```

## 🌐 LAN Access

Доступ к Filmoteka с других устройств в локальной сети (WiFi).

### Quick connect

```bash
# 1. Найти IP вашего Windows-компьютера
ipconfig
# Найдите строку "IPv4-адрес" — например 192.168.1.100

# 2. Открыть на другом устройстве (телефон, планшет, TV)
# → http://<ваш-IP>/
# Например: http://192.168.1.100/
```

Всё должно работать сразу — Docker пробрасывает порт 80 на все сетевые
интерфейсы автоматически.

### Возможные проблемы

**1. Windows Firewall блокирует порт 80**

```powershell
# Windows Admin PowerShell — открыть порт 80 для локальной сети
New-NetFirewallRule -DisplayName "Filmoteka HTTP" -Direction Inbound `
  -Protocol TCP -LocalPort 80 -Action Allow -Profile Private
```

**2. Docker Desktop — WSL2 NAT**

В Docker Desktop → Settings → Resources → Network включите
`Enable host networking` (требуется WSL 2.0+). Без этой опции
некоторые старые версии WSL2 изолируют контейнеры за NAT.

**3. Антивирус блокирует WSL2**

Добавьте исключение для Docker Desktop / WSL2 в настройках
антивируса (Kaspersky, ESET и т.д.).

### Performance notes

- **MP4** — играет напрямую, без нагрузки на сервер
- **MKV** — требует ffmpeg ремукс на сервере (CPU). WiFi может
  быть узким местом для 4K HDR с высоким битрейтом.
  Для стабильного просмотра 4K предпочтительно проводное
  подключение сервера к роутеру.
- Обычное HD (1080p) работает без проблем даже по WiFi.

### mDNS (продвинутый вариант)

Чтобы открывать `http://filmoteka.local/` вместо IP-адреса,
на Windows-хосте можно установить **Bonjour** (входит в iTunes
или отдельно от Apple) или **mDNSResponder**. После установки
добавьте в `C:\Windows\System32\drivers\etc\hosts` строку:

```
127.0.0.1  filmoteka.local
```

Это сделает `http://filmoteka.local/` доступным только на
самом Windows-хосте. Для полноценного mDNS в LAN требуется
настроить mDNS reflector на роутере или в локальной сети.

## Development

### Prerequisites

- Python 3.11+
- Docker + Docker Compose
- ffmpeg (опционально, для MKV в браузере)

### Local setup (без Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# настроить DATABASE_URL на локальный PostgreSQL
alembic upgrade head
filmoteka  # запуск dev-сервера
```

### Tests

```bash
# Полный матрикс (ruff → mypy → unit → integration → e2e)
bash scripts/run-all-checks.sh

# Только unit
pytest tests/unit -v

# Только integration (требуется PostgreSQL)
pytest tests/integration -v

# Только e2e (требуется полный стек)
pytest tests/e2e -v

# Coverage
bash scripts/run-coverage.sh
```

**Известно:** 21 pre-existing test failure (проблемы изоляции данных между
тестами в integration/test_catalog.py, test_importing.py, test_migrations.py).
Не влияют на production-функциональность.

## Known issues

- **Backup** требует `pg_dump` — не установлен в Docker-образе.
  Решение: добавить `postgresql-client` в Dockerfile, либо запускать
  `pg_dump` с хост-машины.
- **Постеры** не обогащаются автоматически при re-scan — после первого
  импорта нужно запустить "Fill missing posters" из admin UI.
- **MKV без ffmpeg** — возвращает 415. Установите ffmpeg в систему или
  используйте Docker (образ включает ffmpeg).
- **Поиск** — `ilike %q%`, требует точного вхождения подстроки.
  Английские названия не найдут фильмы с русскими заголовками.
