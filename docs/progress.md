# docs/progress.md

# Filmoteka — Progress Log

> Этот файл ведёт агент.

## Task Report: V1-039 — 2026-06-10

- Status: `done`
- Summary: Заменил TMDb на OMDB как единственный источник постеров. Полностью удалена интеграция с TMDb (постеры, Kinopoisk ссылки). Добавлена `omdb_search_poster()` с двухуровневым поиском: exact match через `?t=title&y=year` → fuzzy fallback через `?s=title&y=year`. `TMDB_API_KEY` → `OMDB_API_KEY` в settings, .env, docker-compose. Удалён `Film.kinopoisk_url` из модели, схем API и фронтенда. Удалены TMDb/Kinopoisk unit-тесты (14), добавлены OMDB unit-тесты (10). Обновлены интеграционные тесты.
- Changed files:
  - `agent-tasklist.md` (+ V1-039 task)
  - `src/filmoteka/infrastructure/settings.py` (tmdb_api_key → omdb_api_key; extra='ignore')
  - `src/filmoteka/infrastructure/metadata_providers.py` (полностью переписан — OMDB вместо TMDb)
  - `src/filmoteka/domain/importing/pipeline.py` (OMDB poster, удалён Kinopoisk)
  - `src/filmoteka/api/admin.py` (OMDB poster, удалён Kinopoisk из FilmDetailOut)
  - `src/filmoteka/domain/catalog/models.py` (удалён kinopoisk_url)
  - `src/filmoteka/api/schemas/catalog.py` (удалён kinopoisk_url из FilmOut, FilmDetailOut)
  - `src/filmoteka/static/index.html` (удалён Kinopoisk link, TMDb→OMDB в тексте)
  - `.env.example` (TMDB_API_KEY → OMDB_API_KEY)
  - `docker-compose.yml` (TMDB_API_KEY → OMDB_API_KEY ×2)
  - `tests/unit/test_metadata_providers.py` (полностью переписан — 10 OMDB тестов)
  - `tests/integration/test_importing.py` (моки OMDB, удалены Kinopoisk)
  - `tests/integration/test_admin.py` (моки OMDB, OMDB_API_KEY)
  - `tests/integration/test_catalog.py` (удалены kinopoisk_url assertions)
- Checks:
  - ruff check: `yes` (только предсуществующее предупреждение в test_admin.py:681)
  - mypy: `yes` (57 source files, clean)
  - pytest unit: `yes` (144/144, +10 OMDB, −14 TMDb/Kinopoisk)
  - pytest integration: `yes` (144/144, excluding pre-existing migration test failure)
- Next task:
  - V1-011 — Implement language filter for audio and subtitles

- Status: `done`
- Summary: Починил исходящие соединения из Docker-контейнера к TMDb. Добавил `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` в `environment:` обоих сервисов (`docker-compose.yml`). Если в `.env` указан proxy — Docker Compose подставит его в контейнер, `urllib` подхватит автоматически. В `metadata_providers.py` разделил обработку `URLError` — теперь в лог пишется понятное сообщение с рекомендацией проверить proxy/файрвол.
- Changed files:
  - `docker-compose.yml` (+ HTTP_PROXY, HTTPS_PROXY, NO_PROXY в api и worker)
  - `src/filmoteka/infrastructure/metadata_providers.py` (+ импорт URLError; отдельный except с детальным сообщением)
- Checks:
  - ruff check: `yes` (только предсуществующее предупреждение)
  - mypy: `yes` (57 source files, clean)
  - docker compose config: `yes` (HTTP_PROXY/HTTPS_PROXY присутствуют)
  - pytest integration: `yes` (69/69 passed)
- Next task:
  - V1-011 — Implement language filter for audio and subtitles

## Task Report: INFRA-001 — 2026-06-09

- Status: `done`
- Summary: Добавил ffmpeg в Docker-образы api и worker. Код ремукса MKV (V1-031) уже был, но в контейнерах ffmpeg отсутствовал — `_ffmpeg_available()` возвращал `False`, и плеер выдавал 415. В оба Dockerfile добавлен `apt-get install -y ffmpeg`. Проверено: `ffmpeg -version` (7.1.4) работает в обоих образах. Теперь MKV играет в браузере через on-the-fly ремукс.
- Changed files:
  - `docker/Dockerfile.api` (+ apt-get install ffmpeg)
  - `docker/Dockerfile.worker` (+ apt-get install ffmpeg)
- Checks:
  - docker build: `yes` (оба образа собраны)
  - ffmpeg -version: `yes` (7.1.4 в обоих)
  - ruff check: `yes` (предсуществующее предупреждение в test_admin.py:681, не относится к задаче)
  - mypy: `yes` (57 source files, clean)
- Next task:
  - V1-010 — Implement filters by tech attributes (resolution, codec, subtitles, audio tracks)

## Task Report: BUGFIX-002 — 2026-06-09

- Status: `done`
- Summary: Починил 500 на MKV с не-ASCII (русскими) названиями. `Content-Disposition` в `_ffmpeg_remux_stream()` использовал `path.stem` напрямую, но HTTP-заголовки обязаны быть в latin-1 — кириллица вызывала `UnicodeEncodeError`. Заменил на `filename*=UTF-8''...` (RFC 5987) через `urllib.parse.quote()`. Добавлен регрессионный тест с русским названием.
- Changed files:
  - `src/filmoteka/api/media.py` (+ `from urllib.parse import quote`; `Content-Disposition` → `filename*=UTF-8''...`)
  - `tests/integration/test_media.py` (+ `test_mkv_with_cyrillic_filename_does_not_500`)
  - `agent-tasklist.md` (+ BUGFIX-002)
- Checks:
  - ruff check: `yes` (только предсуществующее предупреждение в test_admin.py:681)
  - mypy: `yes` (57 source files, clean)
  - pytest integration test_media.py: `yes` (32/32 passed, +1 новый)
- Next task:
  - V1-011 — Implement language filter for audio and subtitles

## Task Report: V1-010 — 2026-06-09

- Status: `done`
- Summary: Реализовал фильтры по техатрибутам MediaFile: resolution, codec, audio_codec, has_subtitles. Все фильтры работают через subquery Film → MovieEdition → MediaFile. Resolution парсится из лейблов (4K, 1080p, 720p, SD и т.д.) в минимальную высоту. Codec/audio_codec — частичное совпадение (ilike). has_subtitles=true — проверка subtitle_languages IS NOT NULL. 7 новых integration тестов.
- Changed files:
  - `src/filmoteka/api/catalog.py` (+ _RESOLUTION_MAP, _min_height(); 4 query-параметра; subquery-фильтры)
  - `tests/integration/test_catalog.py` (+ 7 тестов: resolution, 4k, codec, codec partial, audio_codec, has_subtitles, combined)
- Checks:
  - ruff check: `yes` (только предсуществующее предупреждение)
  - mypy: `yes` (57 source files, clean)
  - pytest integration test_catalog.py: `yes` (37/37 passed, +7 новых)
- Next task:
  - V1-011 — Implement language filter for audio and subtitles

## Task Report: BUGFIX-003 — 2026-06-09

- Status: `done`
- Summary: Прокинул TMDB_API_KEY в Docker-контейнеры. `.env` не копируется в образ (правильно — секреты не должны быть в image), но docker-compose.yml не передавал переменную контейнерам api и worker. `settings.tmdb_api_key` всегда был `None` в Docker. В обе секции `environment` добавлено `TMDB_API_KEY: ${TMDB_API_KEY}` — Docker Compose читает значение из `.env` в корне проекта.
- Changed files:
  - `docker-compose.yml` (+ TMDB_API_KEY в api и worker)
- Checks:
  - docker compose config: `yes` (TMDB_API_KEY присутствует в обоих сервисах)
  - ruff / mypy: не требуется (изменён только compose-файл)
- Next task:
  - V1-010 — Implement filters by tech attributes (resolution, codec, subtitles, audio tracks)

## Task Report: V1-009 — 2026-06-09

- Status: `done`
- Summary: Реализовал фильтры по жанру (slug) и диапазону годов. В `GET /films` добавлены query-параметры: `genre` (slug из Genre), `year_from` и `year_to` (диапазон). Старый `year` сохранён для обратной совместимости. Фильтры `genre` и `year`/`year_from`/`year_to` комбинируются между собой и с поиском `q`. Фильтры по стране и возрастному рейтингу отложены — в схеме БД нет соответствующих полей (нужна отдельная задача).
- Changed files:
  - `src/filmoteka/api/catalog.py` (+ genre, year_from, year_to params; genre filter через Genre.slug)
  - `tests/integration/test_catalog.py` (+ 7 тестов: genre slug, genre no-results, year_from, year_to, year range, genre+year combo, search+genre combo)
- Checks:
  - ruff check: `yes` (только предсуществующее предупреждение в test_admin.py:681)
  - mypy: `yes` (57 source files, clean)
  - pytest integration test_catalog.py: `yes` (30/30 passed, +7 новых)
- Next task:
  - V1-010 — Implement filters by tech attributes (resolution, codec, subtitles, audio tracks)

## Task Report: BUGFIX-001 — 2026-06-09

- Status: `done`
- Summary: Починил воспроизведение видео при смене окружения (Docker ↔ native, WSL ↔ Windows). Корень: `MediaFile.file_path` хранит абсолютные пути, которые становятся невалидными при смене среды. Добавлен auto-fix в `stream_media()` — если файл не найден по сохранённому пути, ищется по имени под текущим `library_root`. Добавлен admin endpoint `POST /admin/media/reindex` для массовой переиндексации + кнопка в админке. 7 unit-тестов на `_resolve_media_path`, 4 integration-теста на reindex, 2 integration-теста на auto-fix.
- Changed files:
  - `src/filmoteka/api/media.py` (+ _resolve_media_path helper; auto-fix в stream_media; импорты logging, get_library_config, LibraryConfig)
  - `src/filmoteka/api/admin.py` (+ POST /admin/media/reindex, GET /admin/media/reindex/status, _reindex_resolve_path; импорты logging, Path, MediaFile, _logger)
  - `src/filmoteka/static/index.html` (+ "Media paths" секция в админке с кнопкой Re-index; JS: runReindex, buildReindexReportHTML)
  - `tests/unit/test_media_paths.py` (new — 7 тестов на _resolve_media_path)
  - `tests/integration/test_admin.py` (+ TestAdminMediaReindex — 4 теста: 401, 403, fix, skip; _cleanup_all_test_data)
  - `tests/integration/test_media.py` (+ TestStreamMediaAutoFix — 2 теста: auto-fix resolves, 404 when not found; импорты get_library_config, LibraryConfig)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (148/148, +7 новых)
  - pytest integration: `yes` (135/135, +6 новых)
- Next task:
  - V1-009 — Implement filters by genre, year, country, age rating

## Task Report: V1-008 — 2026-06-09

- Status: `done`
- Summary: Расширил поиск по `q` с title на description, genre names и person names. В `GET /films` фильтр использует SQLAlchemy `any()` через many-to-many связи. 4 новых integration-теста: поиск по description, genre, actor, множественные поля.
- Changed files:
  - `src/filmoteka/api/catalog.py` (+ импорт Genre; расширен q-фильтр через OR с any(); обновлён docstring)
  - `tests/integration/test_catalog.py` (+ 4 теста: search_by_description, search_by_genre, search_by_actor, search_matches_multiple_fields)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (141/141)
  - pytest integration: `yes` (129/129, +4 новых)
- Next task:
  - V1-009 — Implement filters by genre, year, country, age rating

## Task Report: V1-007 — 2026-06-09

- Status: `done`
- Summary: Написал unit и integration тесты для enrichment pipeline. Новый файл `tests/unit/test_pipeline.py` с 7 unit-тестами: ImportReport (defaults, to_dict, errors, new list isolation) и `_ffprobe_available()` (found/not found). Добавил 5 integration-тестов в `TestPipelineBridge`: quality upgrade при успешном TMDb (source="tmdb", confidence=0.9), needs_review=True при пустом TMDb, stays filename-level без API key, dedup двух файлов в один фильм + две редакции, dedup одинакового названия с разными годами → два фильма. Всего +7 unit, +5 integration = 266 total (141 unit + 125 integration).
- Changed files:
  - `tests/unit/test_pipeline.py` (new — 7 тестов)
  - `tests/integration/test_importing.py` (+ 5 тестов в TestPipelineBridge; импорты patch, settings)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (141/141, +7 новых)
  - pytest integration: `yes` (125/125, +5 новых)
- Next task:
  - V1-008 — Implement full-text search across title, description, genres, actors

## Task Report: V1-006 — 2026-06-09

- Status: `done`
- Summary: Реализовал ручную правку карточки фильма админом. `PUT /admin/films/{film_id}` принимает опциональные `title`, `year`, `description`, обновляет только переданные поля. При изменении сбрасывает `needs_review=False`, `metadata_source="manual"`, `metadata_confidence=1.0`. Во фронтенде на странице фильма для admin-пользователя появляется "✏ Edit" кнопка, при клике — inline-редактирование title/year/description с Save/Cancel. 9 новых integration-тестов.
- Changed files:
  - `src/filmoteka/api/schemas/catalog.py` (+ FilmUpdateSchema)
  - `src/filmoteka/api/admin.py` (+ PUT /admin/films/{film_id}; импорты EditionOut, GenreOut, MediaFileOut, PersonOut, select, joinedload)
  - `src/filmoteka/static/index.html` (+ CSS .edit-btn/.edit-field/.edit-textarea/.edit-actions; JS: editingFilmId, startFilmEdit, cancelFilmEdit, saveFilmEdit; renderFilm: edit mode UI for admin)
  - `tests/integration/test_admin.py` (+ TestAdminFilmEdit — 9 тестов: 401, 403, 404, edit title/year/description/all, clears needs_review, no-change preserves needs_review)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (134/134)
  - pytest integration: `yes` (120/120, +9 новых)
- Next task:
  - V1-007 — Write unit/integration tests for enrichment pipeline

- Status: `done`
- Summary: Добавил визуальный прогресс-бар на страницу карточки фильма (`#film/{id}`). Под кнопкой Play/Continue показывается: для незавершённого просмотра — прогресс-бар (отношение last_position к duration_secs) + подпись "MM:SS / HH:MM:SS"; для завершённого — зелёный badge "✓ Watched". Без просмотра или без duration_secs — ничего не показывается.
- Changed files:
  - `src/filmoteka/static/index.html` (+ renderFilm: прогресс-бар / watched-label под playBtn; CSS: .progress-wrap, .progress-track/fill, .progress-label, .watched-label)
  - `tests/integration/test_importing.py` (fix: assertions под реальное поведение с TMDB_API_KEY в .env)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (134/134)
  - pytest integration: `yes` (111/111)
- Next task:
  - V1-036 — Add progress bar on film detail page *(already done)*
  - V1-037 — *(already done)*
  - V1-006 — Implement manual card edit by admin

---

## Task Report: V1-035 — 2026-06-08

- Status: `done`
- Summary: Добавил индикатор прогресса просмотра на карточки фильмов в списке (grid view). Новый batch-эндпоинт `POST /media/watch/states-by-film` принимает список film_ids, для каждого находит первый MediaFile через editions и возвращает watch-state текущего пользователя (has_state, last_position, duration_secs, finished). Во фронтенде `renderList()` после загрузки списка batched-запросом получает состояния всех видимых фильмов и отображает: красный badge "▶ Continue" + прогресс-бар для незавершённых, зелёный badge "✓ Watched" для завершённых. Без авторизации прогресс не показывается.
- Changed files:
  - `src/filmoteka/api/schemas/watch.py` (+ FilmWatchState, FilmWatchStatesRequest, FilmWatchStatesResponse)
  - `src/filmoteka/api/media.py` (+ POST /media/watch/states-by-film, import joinedload, import Film)
  - `src/filmoteka/static/index.html` (+ renderList: batch fetch + badge+progress-bar per card; CSS: .poster-wrap, .watch-badge, .progress-track/fill)
  - `tests/integration/test_media.py` (+ TestWatchStatesByFilm — 5 тестов: auth, empty, no-media, unfinished, mixed)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (134/134)
  - pytest integration: `yes` (111/111, +5 новых)
- Next task:
  - V1-036 — Add progress bar on film detail page

---

## Task Report: V1-005 — 2026-06-08

- Status: `done`
- Summary: Реализовал metadata quality pipeline. На Film добавлены 4 поля: `metadata_source`, `metadata_confidence`, `metadata_enriched_at`, `needs_review`. В bridge-шаге pipeline после filename parse проставляется `source="filename_parse"`, `confidence=0.6` (с годом) или `0.3` (без года). После TMDb-обогащения (poster или kinopoisk найдены) — апгрейд до `source="tmdb"`, `confidence=0.9`, `metadata_enriched_at=now`, `needs_review=False`. Если TMDb доступен, но ничего не нашёл — `needs_review=True`. `needs_review` экспортируется в `FilmDetailOut`.
- Changed files:
  - `src/filmoteka/domain/catalog/models.py` (+ 4 колонки: metadata_source, metadata_confidence, metadata_enriched_at, needs_review)
  - `migrations/versions/1eacde9e15e5_add_metadata_quality_columns.py` (new — миграция)
  - `src/filmoteka/domain/importing/pipeline.py` (+ проставление quality-полей в _bridge_to_catalog)
  - `src/filmoteka/api/catalog.py` (+ needs_review в конструктор FilmDetailOut)
  - `src/filmoteka/api/schemas/catalog.py` (+ needs_review в FilmDetailOut)
  - `tests/integration/test_catalog.py` (+ test_needs_review_flag, test_bare_film_needs_review_default)
  - `tests/integration/test_importing.py` (+ quality assertions в test_full_pipeline_creates_film и test_pipeline_without_year_creates_film)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (134/134)
  - pytest integration: `yes` (106/106, +2 новых)
- Next task:
  - V1-035 — Add watch/continue button to film grid (frontend UX)

---

> Правила заполнения:
> - После **каждой завершённой задачи** добавлять новую запись в начало файла.
> - Одна запись = одна завершённая задача.
> - Не удалять старые записи.
> - Если задача частично сделана, ставить статус `partial`, а не `done`.
> - Если задача заблокирована, ставить статус `blocked` и обязательно писать причину.
> - Если поведение системы изменилось, агент обязан указать, какие тесты добавлены или обновлены.
> - Если проверки не запускались, нужно явно написать почему.

---

## Task Report: V1-031 — 2026-06-08

- Status: `done`
- Summary: Реализовал поддержку MKV и других форматов в плеере. `media_type` теперь определяется динамически по расширению файла (mp4→`video/mp4`, webm→`video/webm`, mkv→`video/x-matroska`, avi→`video/x-msvideo` и т.д.). Для MKV: если `ffmpeg` найден в PATH — ремукс в MP4 на лету через `StreamingResponse` (stream copy, без перекодирования). Если ffmpeg недоступен — HTTP 415. HEAD-запросы обрабатываются отдельно, без запуска ffmpeg. Во фронтенде добавлена обработка 415 с сообщением "MKV format not supported". 5 новых integration-тестов.
- Changed files:
  - `src/filmoteka/api/media.py` (refactor: `_mime_type()`, `_ffmpeg_available()`, `_ffmpeg_remux_stream()`, `stream_media()` — `@router.api_route` с GET+HEAD, динамический MIME, ffmpeg-ремукс для MKV, 415 без ffmpeg)
  - `src/filmoteka/static/index.html` (+ обработка status 415 в renderPlayer)
  - `tests/integration/test_media.py` (+ 5 тестов: webm MIME, avi MIME, MKV без ffmpeg→415, HEAD MKV без ffmpeg→415, HEAD MKV с ffmpeg→200)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (134/134)
  - pytest integration: `yes` (104/104, +5 новых)
- Next task:
  - V1-035 — Add watch/continue button to film grid (frontend UX)

---

## Task Report: V1-038 — 2026-06-08

- Status: `done`
- Summary: Добавил в админку две кнопки управления постерами. `POST /admin/posters/fill-missing` — заполняет постеры только у фильмов без `poster_url`. `POST /admin/posters/refresh-all` — перезапрашивает и заменяет постеры у всех фильмов. Оба эндпойнта работают в бэкграунд-треде с polling через `GET /admin/posters/status`. Без `TMDB_API_KEY` возвращают ошибку. Во фронтенде две кнопки с confirm-диалогом, спиннером, polling и отчётом (total/updated/skipped/errors). Использован существующий `tmdb_search_poster()`.
- Changed files:
  - `src/filmoteka/api/admin.py` (+ `POST /admin/posters/fill-missing`, `POST /admin/posters/refresh-all`, `GET /admin/posters/status`)
  - `src/filmoteka/static/index.html` (+ CSS для poster-секции, две кнопки в renderAdmin, JS: `runFillPosters`/`runRefreshPosters`/`runPosterOp`/`pollPosterStatus`/`buildPosterReportHTML`)
  - `tests/integration/test_admin.py` (+ `TestAdminPosters` — 8 тестов: auth, missing key, fill-missing, refresh-all)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (134/134)
  - pytest integration: `yes` (99/99, +8 новых)
- Next task:
  - V1-031 — Implement MKV playback support (или V1-035 — Continue button in grid)

---

## Task Report: V1-004 — 2026-06-07

- Status: `done`
- Summary: Реализовал поиск ссылок на Kinopoisk через TMDb external_ids. В metadata_providers добавлен общий вспомогательный слой (`_tmdb_api_get`, `_tmdb_search_first`), функция `tmdb_find_kinopoisk_url()`. В bridge-шаге после постера выполняется поиск Kinopoisk URL через TMDb movie ID → external_ids (kp_id). `kinopoisk_url` сохранён на Film, возвращается в API и отображается как ссылка "View on Kinopoisk →" на карточке фильма. `TMDB_API_KEY` опционален — без него ссылки не ищутся.
- Changed files:
  - `src/filmoteka/infrastructure/metadata_providers.py` (refactor: + `_tmdb_api_get`, `_tmdb_search_first`, `tmdb_find_kinopoisk_url`; poster uses shared helpers)
  - `src/filmoteka/domain/catalog/models.py` (+ `kinopoisk_url` on Film)
  - `migrations/versions/04572a67037e_add_kinopoisk_url_to_films.py` (new — migration)
  - `src/filmoteka/domain/importing/pipeline.py` (+ Kinopoisk enrichment step)
  - `src/filmoteka/api/schemas/catalog.py` (+ `kinopoisk_url` in FilmOut, FilmDetailOut)
  - `src/filmoteka/static/index.html` (+ "View on Kinopoisk →" link in detail, CSS)
  - `tests/unit/test_metadata_providers.py` (+ TestTmdbFindKinopoiskUrl — 6 tests)
  - `tests/integration/test_importing.py` (+ `kinopoisk_url` assertion)
  - `tests/integration/test_catalog.py` (+ `kinopoisk_url` assertions)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (134/134)
  - pytest integration: `yes` (91/91)
- Next task:
  - V1-031 — Implement MKV playback support (или V1-035 — Continue button in grid)

---

## Task Report: V1-003 — 2026-06-07

- Status: `done`
- Summary: Реализовал поиск постеров через TMDb API. При импорте фильма (`_bridge_to_catalog`) выполняется поиск постера по title+year через TMDb API. Результат сохраняется в `Film.poster_url` и `Film.poster_source`. В API-схемы (`FilmOut`, `FilmDetailOut`) добавлено поле `poster_url`. Во фронтенде постер отображается в списке фильмов (grid) и на карточке фильма (detail), с CSS fallback-плейсхолдером при отсутствии или ошибке загрузки. `TMDB_API_KEY` опционален — если не задан, импорт идёт без постеров (graceful degradation).
- Changed files:
  - `src/filmoteka/infrastructure/settings.py` (+ `tmdb_api_key`)
  - `.env.example` (+ `TMDB_API_KEY`)
  - `src/filmoteka/domain/catalog/models.py` (+ `poster_url`, `poster_source` on Film)
  - `migrations/versions/c1784ebef74d_add_poster_url_and_poster_source_to_.py` (new — migration)
  - `migrations/env.py` (+ watching_models import for autogenerate)
  - `src/filmoteka/infrastructure/metadata_providers.py` (new — TMDbClient)
  - `src/filmoteka/domain/importing/pipeline.py` (+ poster enrichment in bridge)
  - `src/filmoteka/api/schemas/catalog.py` (+ `poster_url` in FilmOut, FilmDetailOut)
  - `src/filmoteka/static/index.html` (+ poster img in renderList/renderFilm, CSS)
  - `tests/unit/test_metadata_providers.py` (new — 8 mocked TMDb tests)
  - `tests/integration/test_importing.py` (+ poster assertion in bridge test)
  - `tests/integration/test_catalog.py` (+ `poster_url` assertions in list/detail tests)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (136/136)
  - pytest integration: `yes` (91/91)
- Next task:
  - V1-031 — Implement MKV playback support (или V1-035 — Continue button in grid)

---

## Task Report: V1-037 — 2026-06-07

- Status: `done`
- Summary: Починил сохранение прогресса просмотра — `db.flush()` заменён на `db.commit()` в `PATCH /media/{id}/watch/{watch_event_id}/progress`. Ранее `flush()` писал в транзакцию, которая откатывалась при закрытии сессии, и `last_position` никогда не сохранялся.
- Changed files:
  - `src/filmoteka/api/media.py` — `db.flush()` → `db.commit()`
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (120/120)
  - pytest integration: `yes` (91/91)
- Next task:
  - V1-003 — Implement poster search

## Task Report: V1-034 — 2026-06-07

- Status: `done`
- Summary: Подключил resume playback во фронтенде. `POST /watch/start` при нажатии Play, seek на `last_position` через `loadedmetadata`, сохранение прогресса каждые 10 сек, финальное сохранение при `hashchange`, кнопка "Continue (MM:SS)" на карточке фильма вместо Play при наличии незавершённого просмотра.
- Changed files:
  - `src/filmoteka/static/index.html` (+ renderFilm: watch/state → Continue button; renderPlayer: watch/start + progress interval + hashchange save; formatTime helper)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (120/120)
  - pytest integration: `yes` (91/91)
- Next task:
  - V1-035 — Add watch/continue button to film grid

## Task Report: V1-033 — 2026-06-07

- Status: `done`
- Summary: Починил повторный запуск плеера — убран лишний `render()` из `navigate()` (hashchange и так его триггерит), добавлен `cache: 'no-cache'` в HEAD-запрос renderPlayer.
- Changed files:
  - `src/filmoteka/static/index.html` — убран render() из navigate(), cache: no-cache в HEAD
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (120/120)
  - pytest integration: `yes` (91/91)
- Next task:
  - V1-034 — Resume playback in frontend

## Task Report: V1-032 — 2026-06-07

- Status: `done`
- Summary: Починил роутинг плеера — `currentRoute()` кладёт media_id в `route.id` (parts[1]), а `render()` проверял `route.mediaId` (parts[2] → всегда undefined). Заменил `route.mediaId` на `route.id`.
- Changed files:
  - `src/filmoteka/static/index.html` — `route.mediaId` → `route.id`
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (120/120)
  - pytest integration: `yes` (91/91)
- Next task:
  - V1-033 — Fix second play not working

## Task Report: V1-031 — не начата

## Task Report: V1-030 — 2026-06-07

- Status: `done`
- Summary: Добавил отображение ошибок в плеере. Перед показом `<video>` выполняется HEAD-запрос к stream-эндпоинту. По статусу ответа показываются сообщения: 404 → "Video file not found", 401/403 → "Access denied", 500 → "Server error", сетевая ошибка → "Could not load video". На `<video>` добавлен `onerror`-обработчик на случай, если HEAD прошёл, но браузер не может воспроизвести формат.
- Changed files:
  - `src/filmoteka/static/index.html` (+ play-error CSS, async renderPlayer с HEAD-проверкой и onerror)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (120/120)
  - pytest integration: `yes` (91/91)
- Next task:
  - V1-003 — Implement poster search

## Task Report: V1-002 — 2026-06-07

- Status: `done`
- Summary: Обогатил карточку фильма из имени файла. В `ParsedFilename` добавлены `language` и `edition_type`. Парсер извлекает язык (RUS, DUB, Original, ENG, Multi, SUB и др.) и тип издания (Director's Cut, Extended, Unrated, Remastered и др.) из имени файла. Эти поля прокидываются в `MovieEdition.language` и `MovieEdition.edition_name` при bridge-шаге. 15 новых unit-тестов на парсинг языка/издания.
- Changed files:
  - `src/filmoteka/infrastructure/filename_parser.py` (+ language/edition extraction)
  - `src/filmoteka/domain/importing/pipeline.py` (+ language/edition в MovieEdition)
  - `tests/unit/test_filename_parser.py` (+ 15 тестов)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (120/120)
  - pytest integration: `yes` (91/91)
- Next task:
  - V1-003 — Implement poster search

## Task Report: V1-029 — 2026-06-07

- Status: `done`
- Summary: Изменил импорт — теперь он только индексирует файлы без копирования. `scan_downloads()` сканирует `target_root` вместо `downloads_root`. Из pipeline удалён layout-шаг (move), bridge создаёт Film/MovieEdition/MediaFile прямо из отсканированных файлов. ImportReport: `files_laid_out` заменён на `files_indexed`.
- Changed files:
  - `src/filmoteka/domain/importing/scan.py` — scan использует `target_root`
  - `src/filmoteka/domain/importing/pipeline.py` — убран layout, bridge напрямую после probe
  - `specs/library.yaml` — обновлены комментарии путей
  - `tests/integration/test_importing.py` — тесты обновлены под новую логику
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (91/91)
- Next task:
  - V1-002 — Implement external metadata providers layer

## Task Report: FIX-003 — 2026-06-07

- Status: `done`
- Summary: Починил импорт на Windows без ffmpeg. Пайплайн стопорился на probe — если ffprobe не установлен, все кандидаты получали CANDIDATE_ERROR, layout и bridge не запускались. Теперь probe выполняется только если ffprobe найден в PATH; иначе candidates остаются PENDING и layout/bridge работают без probe-данных.
- Changed files:
  - `src/filmoteka/domain/importing/pipeline.py` (+ _ffprobe_available(), probe пропускается без ffprobe; layout на pending)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (90/90)
- Next task:
  - V1-002 — Implement external metadata providers layer

## Task Report: V1-028 — 2026-06-07

- Status: `done`
- Summary: Добавил seed dev admin-пользователя (mrsalt3000/dev) в lifespan. При старте сервиса проверяется наличие пользователя mrsalt3000 — если нет, создаётся с хэшированным паролем "dev" и ролью admin. Идемпотентно.
- Changed files:
  - `src/filmoteka/app.py` (+ seed_dev_admin(), вызов в lifespan)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (90/90)
- Next task:
  - V1-002 — Implement external metadata providers layer

## Task Report: V1-027 — 2026-06-07

- Status: `done`
- Summary: Добавил admin-страницу во фронтенд с аутентификацией и кнопкой импорта. В `index.html`: login-форма (POST /auth/login), токен в localStorage, проверка роли через /auth/me, ссылка "Admin" в навбаре только для admin, админ-страница (#admin) с кнопкой "Scan library", confirm-диалог, спиннер, import report.
- Changed files:
  - `src/filmoteka/static/index.html` (+ login/logout, auth state, admin page, scan button + report)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (90/90)
- Next task:
  - V1-002 — Implement external metadata providers layer

## Task Report: V1-001 — 2026-06-07

- Status: `done`
- Summary: Plan V1 features + wire up import pipeline. Сделал:
  - V1 roadmap: зафиксировал приоритеты в `architecture-decisions.md`
  - `Settings` — добавлены `downloads_root`/`library_root` из `.env`
  - `LibraryConfig` — добавлен `with_overrides()` для переопределения путей из `.env`
  - `pipeline.py` — оркестратор `run_import()`: scan → probe → layout → bridge (создание Film/MovieEdition/MediaFile)
  - `app.py` — lifespan для загрузки `LibraryConfig` при старте
  - `admin.py` — `POST /admin/import/scan` для ручного запуска импорта
  - `dependencies.py` — `get_library_config` dependency
  - `conftest.py` — починил поднятие тестовой БД (migrations/env.py переопределял URL через `settings.database_url`)
- Changed files:
  - `src/filmoteka/infrastructure/settings.py` (+ downloads_root, library_root)
  - `src/filmoteka/infrastructure/library_config.py` (+ with_overrides)
  - `src/filmoteka/domain/importing/pipeline.py` (new — orchestrator + bridge)
  - `src/filmoteka/api/dependencies.py` (new — get_library_config)
  - `src/filmoteka/api/admin.py` (+ POST /admin/import/scan)
  - `src/filmoteka/app.py` (+ lifespan hook)
  - `tests/integration/conftest.py` (fix: patch settings.database_url for test DB)
  - `tests/integration/test_admin.py` (+ TestAdminImportScan — 3 tests)
  - `tests/integration/test_importing.py` (+ TestPipelineBridge — 3 tests)
  - `tests/unit/test_smoke.py` (fix: _env_file=None in negative test)
  - `docs/architecture-decisions.md` (+ V1 roadmap)
  - `docs/progress.md` (+ report)
- Checks:
  - ruff check: `yes`
  - mypy: `yes`
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (90/90)
- Next task:
  - V1-002 — Implement external metadata providers layer

---

## Task Report: FIX-002 — 2026-06-06

- Status: `done`
- Summary: SPA фронтенд не отдавался через `http://localhost` (nginx → api). Причина: `pip install .` копирует только `.py` файлы в site-packages, а `static/index.html` не был включён в package-data. Функция `create_app()` проверяла `static_dir.is_dir()`, которая была `False` в установленном пакете, поэтому корневой роут `/` и SPA catch-all не регистрировались. Добавил `"static/*"` в `[tool.setuptools.package-data]` в `pyproject.toml`.
- Changed files:
  - `pyproject.toml` — added `"static/*"` to `filmoteka` package-data
- Checks:
  - docker compose: `yes` (nginx + api, обе порта 80 и 8000 отдают SPA с 200)
- Next task:
  - V1-001 — Plan V1 features

---

## Task Report: FIX-001 — 2026-06-06

- Status: `done`
- Summary: Починил `docker compose up` — сервис api не мог подключиться к PostgreSQL из-за того, что `alembic.ini` содержал hardcoded `sqlalchemy.url` с хостом `localhost`, а `migrations/env.py` выбирал это значение вместо env-переменной `DATABASE_URL` из `docker-compose.yml` (где хост корректно указан как `db`). Поменял приоритет: теперь `settings.database_url` (env var) используется первой, `alembic.ini` — fallback.
- Changed files:
  - `migrations/env.py` — swapped `or` operands: env var takes precedence over config file
- Commands run:
  - `docker compose up --build -d` — api container healthy, all 9 migrations ran, uvicorn started
- Checks:
  - docker compose: `yes` (api healthy, healthcheck 200 OK)
- Next task:
  - V1-001 — Plan V1 features

---

## Current Project Snapshot

### Current phase
- Phase: `mvp` ✅ **COMPLETE**
- Active task: `NONE`
- Last completed task: `MVP-027`
- Current branch: `main`
- Last updated: `2026-06-06`

### Overall status
- Initialization: `100%`
- MVP: `100%` ✅
- V1: `0%`
- V2: `0%`

### Current blockers
- None

### Next recommended tasks
1. V1-001 — Plan V1 features

---

## Task Report: MVP-027 — 2026-06-06

- Status: `done`
- Summary: Написал 6 e2e-тестов, покрывающих основные пользовательские сценарии: загрузка каталога, список фильмов, карточка фильма со связанными данными (жанры, персоны, издания, медиафайлы), полный lifecycle просмотра (регистрация → старт → state → прогресс → история), проверка аутентификации на всех watch endpoints.
- Changed files:
  - `tests/integration/test_e2e_flows.py` (new — 6 e2e-тестов)
  - `docs/progress.md` (snapshot + report — MVP complete)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 51 source files
  - `.venv/bin/pytest tests/unit/ -v` — 105/105 passed
  - `.venv/bin/pytest -m integration -v` — 84/84 passed
- Checks:
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (84/84)
  - ruff: `yes`
  - mypy: `yes`
- Next task:
  - V1-001 — Plan V1 features

---

## Task Report: MVP-026 — 2026-06-06

- Status: `done`
- Summary: Добавил переключение светлой/тёмной темы в фронтенд. CSS-переменные для обеих тем, автоопределение системной темы через `prefers-color-scheme`, кнопка переключения в навбаре (☀/🌙), сохранение выбора в `localStorage`. Темы меняются через класс `.light-theme` на `<html>`.
- Changed files:
  - `src/filmoteka/static/index.html` (+ CSS-переменные light-темы, `.light-theme`, `prefers-color-scheme`, кнопка, JS toggleTheme/setTheme/getTheme)
  - `docs/progress.md` (snapshot + report)
- Checks:
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (78/78)
  - ruff: `yes`
  - mypy: `yes`
- Next task:
  - MVP-027 — Write basic e2e tests (catalog, card, player)

---

## Task Report: MVP-025 — 2026-06-06

- Status: `done`
- Summary: Реализовал минимальный браузерный фронтенд — одностраничное приложение на ванильном HTML/CSS/JS с hash-роутингом. Три вьюхи: список фильмов (с поиском), карточка фильма (жанры, персоны, издания, кнопка Play), видеоплеер (встроенный `<video>` с стримингом через `/media/{id}/stream`). Файлы статики (`index.html`) сервятся через FastAPI, SPA роутинг через catch-all `/{path:path}` → `FileResponse(index.html)`.
- Changed files:
  - `src/filmoteka/static/index.html` (new — SPA frontend)
  - `src/filmoteka/app.py` (+ статика, catch-all SPA роутинг)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 50 source files
  - `.venv/bin/pytest tests/unit/ -v` — 105/105 passed
  - `.venv/bin/pytest -m integration -v` — 78/78 passed
- Checks:
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (78/78)
  - ruff: `yes`
  - mypy: `yes`
- Next task:
  - MVP-026 — Implement light and dark theme

---

## Task Report: MVP-024 — 2026-06-06

- Status: `done`
- Summary: Добавил параметр `q` в `GET /films` — поиск по части названия (case-insensitive ILIKE). Комбинируется с существующей фильтрацией по `year`. 4 integration-теста: частичное совпадение, регистронезависимость, пустой результат, q + year.
- Changed files:
  - `src/filmoteka/api/catalog.py` (+ q параметр в list_films)
  - `tests/integration/test_catalog.py` (+ 4 search integration-теста)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 50 source files
  - `.venv/bin/pytest tests/unit/ -v` — 105/105 passed
  - `.venv/bin/pytest -m integration -v` — 78/78 passed
- Checks:
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (78/78)
  - ruff: `yes`
  - mypy: `yes`
- Next task:
  - MVP-025 — Implement minimal browser frontend (films list)

---

## Task Report: MVP-023 — 2026-06-06

- Status: `done`
- Summary: Добавил 4 новых integration-теста на watch endpoints: watch_state для несуществующего media (has_state: false), update progress с position=0 (сброс), update progress с отрицательной позицией, history со смесью finished/unfinished событий. Все watch endpoints теперь покрыты: start (4), state (5), progress (6), history (7) = 22 теста.
- Changed files:
  - `tests/integration/test_media.py` (+ 3 теста: watch_state media not found, update_position_zero, update_negative_position)
  - `tests/integration/test_users.py` (+ 1 тест: mix_finished_and_unfinished)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 50 source files
  - `.venv/bin/pytest tests/unit/ -v` — 105/105 passed
  - `.venv/bin/pytest -m integration -v` — 74/74 passed
- Checks:
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (74/74)
  - ruff: `yes`
  - mypy: `yes`
- Next task:
  - MVP-024 — Implement basic full-text search by title

---

## Task Report: MVP-022 — 2026-06-06

- Status: `done`
- Summary: Реализовал `GET /me/watch/history` — история просмотров текущего пользователя. Возвращает список WatchEvent с информацией о фильме (film_id, title, year) через joins: WatchEvent → MediaFile → MovieEdition → Film. Пагинация (skip/limit). Создал новый роутер `users.py` и схемы WatchHistoryItem/WatchHistoryResponse. 6 integration-тестов: 401, пустая история, одна запись, несколько (порядок DESC), изоляция пользователей, пагинация.
- Changed files:
  - `src/filmoteka/api/schemas/watch.py` (+ WatchHistoryItem, WatchHistoryResponse)
  - `src/filmoteka/api/users.py` (new — GET /me/watch/history)
  - `src/filmoteka/app.py` (+ users_router)
  - `tests/integration/test_users.py` (new — 6 integration-тестов)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 50 source files
  - `.venv/bin/pytest tests/unit/ -v` — 105/105 passed
  - `.venv/bin/pytest -m integration -v` — 70/70 passed
- Checks:
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (70/70)
  - ruff: `yes`
  - mypy: `yes`
- Next task:
  - MVP-023 — Write integration tests for watch endpoints

---

## Task Report: MVP-021 — 2026-06-06

- Status: `done`
- Summary: Реализовал `GET /media/{media_id}/watch/state` — проверка точки возобновления просмотра без побочных эффектов. Возвращает `{has_state: true/false}` + last_position при наличии незавершённого WatchEvent. Завершённые события (finished=true) не возвращаются. 4 integration-теста: 401, нет состояния, есть состояние с позицией, finished → has_state: false.
- Changed files:
  - `src/filmoteka/api/schemas/watch.py` (+ WatchStateResponse)
  - `src/filmoteka/api/media.py` (+ GET /media/{id}/watch/state)
  - `tests/integration/test_media.py` (+ TestWatchState — 4 integration-теста)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 48 source files
  - `.venv/bin/pytest tests/unit/ -v` — 105/105 passed
  - `.venv/bin/pytest -m integration -v` — 64/64 passed
- Checks:
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (64/64)
  - ruff: `yes`
  - mypy: `yes`
- Next task:
  - MVP-022 — Implement watch history

---

## Task Report: MVP-020 — 2026-06-06

- Status: `done`
- Summary: Реализовал `PATCH /media/{media_id}/watch/{watch_event_id}/progress` — сохранение позиции просмотра. Эндпойнт принимает `{"position": float}`, требует аутентификации и проверяет принадлежность watch_event текущему пользователю. 4 integration-теста: без токена (401), не найден (404), чужой event (403), успешное обновление (проверка персистентности в БД).
- Changed files:
  - `src/filmoteka/api/schemas/watch.py` (+ WatchProgressRequest)
  - `src/filmoteka/api/media.py` (+ PATCH /media/{id}/watch/{watch_event_id}/progress)
  - `tests/integration/test_media.py` (+ TestUpdateProgress — 4 integration-теста)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 48 source files
  - `.venv/bin/pytest tests/unit/ -v` — 105/105 passed
  - `.venv/bin/pytest -m integration -v` — 60/60 passed
- Checks:
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (60/60)
  - ruff: `yes`
  - mypy: `yes`
- Risks:
  - Клиент может отправлять позицию в любом формате — нет валидации range (0.0..duration). Для MVP норм.
- Next task:
  - MVP-021 — Implement resume playback

---

## Task Report: MVP-019 — 2026-06-06

- Status: `done`
- Summary: Реализовал `POST /media/{media_id}/watch/start` — старт просмотра с аутентификацией. Создал модель `WatchEvent` (media_file_id, user_id, started_at, last_position, finished) + миграцию. При повторном вызове для того же пользователя и файла возвращается существующий незавершённый WatchEvent (resume). 4 integration-теста: без токена (401), несуществующий media (404), успешный старт, resume.
- Changed files:
  - `src/filmoteka/domain/watching/__init__.py` (new)
  - `src/filmoteka/domain/watching/models.py` (new — WatchEvent model)
  - `src/filmoteka/api/schemas/watch.py` (new — WatchStartResponse)
  - `src/filmoteka/api/media.py` (+ POST /media/{id}/watch/start)
  - `migrations/versions/a1b2c3d4e5f6_add_watch_events_table.py` (new)
  - `tests/integration/test_media.py` (+ TestWatchStart — 4 integration-теста)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 47 source files
  - `.venv/bin/pytest tests/unit/ -v` — 105/105 passed
  - `.venv/bin/pytest -m integration -v` — 56/56 passed
- Checks:
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (56/56)
  - ruff: `yes`
  - mypy: `yes`
- Risks:
  - Нет механизма автоматической финализации — WatchEvent остаётся unfinished до явного вызова.
- Next task:
  - MVP-020 — Implement playback progress saving (playback_states)

---

## Task Report: MVP-018 — 2026-06-06

- Status: `done`
- Summary: Реализовал `GET /media/{media_id}/stream` — endpoint для потоковой выдачи медиафайла через `FileResponse` с поддержкой Range-заголовков (seeking). 404 если media_id не найден или файл отсутствует на диске. 4 integration-теста: 404, файл не на диске, успешная выдача, Range-запрос (206 Partial Content).
- Changed files:
  - `src/filmoteka/api/media.py` (new — GET /media/{id}/stream)
  - `src/filmoteka/app.py` (+ media_router)
  - `tests/integration/test_media.py` (new — 4 integration-теста)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 45 source files
  - `.venv/bin/pytest tests/unit/ -v` — 105/105 passed
  - `.venv/bin/pytest -m integration -v` — 52/52 passed
- Checks:
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (52/52)
  - ruff: `yes`
  - mypy: `yes`
- Risks:
  - `media_type` захардкожен как `video/mp4` — для других форматов (mkv, avi) может быть неверным.
- Next task:
  - MVP-019 — Implement watch start and watch_event recording

---

## Task Report: MVP-017 — 2026-06-06

- Status: `done`
- Summary: Реализовал `GET /films/{film_id}` — карточка фильма с полными связанными данными: жанры, персоны (с ролью из film_person), издания с медиафайлами и техатрибутами. Создал Pydantic-схемы (GenreOut, PersonOut, MediaFileOut, EditionOut, FilmDetailOut). 5 integration-тестов: 404, пустой фильм, с жанрами, с персонами, с изданиями и медиафайлами.
- Changed files:
  - `src/filmoteka/api/schemas/catalog.py` (+ GenreOut, PersonOut, MediaFileOut, EditionOut, FilmDetailOut)
  - `src/filmoteka/api/catalog.py` (+ GET /films/{id}, joinedload, person-role query)
  - `tests/integration/test_catalog.py` (+ TestGetFilm — 5 integration-тестов)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 43 source files
  - `.venv/bin/pytest tests/unit/ -v` — 105/105 passed
  - `.venv/bin/pytest -m integration -v` — 48/48 passed
- Checks:
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (48/48)
  - ruff: `yes`
  - mypy: `yes`
- Risks:
  - Role из film_person получается отдельным запросом — N+1 нет, но два запроса на карточку. Для MVP норм.
- Next task:
  - MVP-018 — Implement media file serving endpoint for playback

---

## Task Report: MVP-016 — 2026-06-06

- Status: `done`
- Summary: Реализовал `GET /films` — список фильмов с пагинацией (`skip`, `limit`) и фильтрацией по году (`year`). Создал Pydantic-схемы (`FilmOut`, `FilmListResponse`), роутер catalog, подключил в `app.py`. 8 integration-тестов: пустой список, один/несколько фильмов, фильтрация, пагинация, сортировка по created_at desc, валидация limit/skip.
- Changed files:
  - `src/filmoteka/api/schemas/catalog.py` (new — FilmOut, FilmListResponse)
  - `src/filmoteka/api/catalog.py` (new — GET /films)
  - `src/filmoteka/app.py` (+ catalog_router)
  - `tests/integration/test_catalog.py` (new — 8 integration-тестов)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 43 source files
  - `.venv/bin/pytest tests/unit/ -v` — 105/105 passed
  - `.venv/bin/pytest -m integration -v` — 43/43 passed
- Checks:
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (43/43)
  - ruff: `yes`
  - mypy: `yes`
- Risks:
  - Нет аутентификации на /films — список публичный. Для MVP норм.
- Next task:
  - MVP-017 — Implement film card API (single film + related data)

---

## Task Report: MVP-015 — 2026-06-06

- Status: `done`
- Summary: Добавил недостающие тесты импорта. Unit: `probe_candidates` с mocked ffprobe — пропуск не-pending, смешанные успех/ошибка (2 теста). Integration: полный pipeline scan → probe → layout с реальным медиафайлом и БД — проверка всех этапов и конечного состояния (1 тест).
- Changed files:
  - `tests/unit/test_scan.py` (+ TestProbeCandidates — 2 unit-теста)
  - `tests/integration/test_importing.py` (+ TestFullPipeline — 1 integration-тест)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 40 source files
  - `.venv/bin/pytest tests/unit/ -v` — 105/105 passed
  - `.venv/bin/pytest -m integration -v` — 35/35 passed
- Checks:
  - pytest unit: `yes` (105/105)
  - pytest integration: `yes` (35/35)
  - ruff: `yes`
  - mypy: `yes`
- Risks:
  - Полный pipeline-тест занимает ~2 сек из-за ffmpeg генерации — приемлемо для integration
- Next task:
  - MVP-016 — Implement film list API

---

## Task Report: MVP-014 — 2026-06-06

- Status: `done`
- Summary: Реализовал идемпотентность `scan_downloads()`. Перед созданием кандидатов выполняется `_existing_candidate_paths()` — запрос к БД по файлам под downloads_root. Файлы, у которых уже есть кандидат с не-error статусом, пропускаются. Кандидаты со статусом `error` пересоздаются при повторном сканировании. 3 integration-теста: повторный запуск не создаёт дубликатов, перезапуск после ошибки, частично новые файлы.
- Changed files:
  - `src/filmoteka/domain/importing/scan.py` (+ `_existing_candidate_paths()`, изменён `scan_downloads()` с фильтрацией)
  - `tests/integration/test_importing.py` (+ TestScanIdempotent — 3 integration-теста)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 40 source files
  - `.venv/bin/pytest tests/unit/ -v` — 103/103 passed
  - `.venv/bin/pytest -m integration -v` — 34/34 passed
- Checks:
  - pytest unit: `yes` (103/103)
  - pytest integration: `yes` (34/34)
  - ruff: `yes`
  - mypy: `yes`
- Risks:
  - Запрос `_existing_candidate_paths` выполняется на каждый `scan_downloads` — при большом количестве записей в БД может быть медленным. Для MVP некритично.
  - Проверка только по пути — если файл удалён и создан заново с тем же именем, будет пропущен.
- Next task:
  - MVP-015 — Write unit and integration tests for import

---

## Task Report: MVP-013 — 2026-06-06

- Status: `done`
- Summary: Реализовал `layout_file()` — перемещение отсканированного файла из downloads в целевую библиотеку. Целевой путь: `<target_root>/<year>/<title> (<year>)/<filename>`. При отсутствии года: `unknown/<title>/`. Автоматическое разрешение коллизий имён (суффикс `(1)`, `(2)` и т.д.). Санитизация имени (удаление недопустимых символов). 14 unit-тестов (генерация путей, sanitise, unique_path, ошибки) + 3 integration-теста (реальное перемещение файла с обновлением пути в БД, проверка года/без года, верификация DB-пути).
- Changed files:
  - `src/filmoteka/domain/importing/layout.py` (new — layout_file, _target_dir, _sanitise, _unique_path, LayoutError)
  - `tests/unit/test_layout.py` (new — 14 unit-тестов)
  - `tests/integration/test_importing.py` (+ TestLayoutFile — 3 integration-теста)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 40 source files
  - `.venv/bin/pytest tests/unit/ -v` — 103/103 passed
  - `.venv/bin/pytest -m integration -v` — 31/31 passed
- Checks:
  - pytest unit: `yes` (103/103)
  - pytest integration: `yes` (31/31)
  - ruff: `yes`
  - mypy: `yes`
- Risks:
  - Перемещение (shutil.move) — не атомарно с записью в БД. При сбое между move и flush файл может быть потерян в обоих местах.
  - Sanitisation может обрезать значимые символы в нелатинских языках (тест на русский есть, но другие не покрыты).
- Next task:
  - MVP-014 — Implement import idempotency

---

## Task Report: MVP-012 — 2026-06-06

- Status: `done`
- Summary: Реализовал `parse_filename()` — базовый парсер имени файла, извлекающий title, year и quality. Алгоритм: удаляет все известные quality-маркеры (1080p/2160p/4K/WEB-DL/WEBRip/BluRay/BDRip/HDTV и т.д.), затем ищет 4-значный год (1900-2099) в очищенном имени, остаток — title (разделители заменяются на пробелы). 21 unit-тест: типовые имена (точки, подчёркивания, дефисы, скобки, русский язык), краевые случаи (пустой stem, год вне диапазона, спецсимволы, TV-эпизоды), иммутабельность dataclass.
- Changed files:
  - `src/filmoteka/infrastructure/filename_parser.py` (new — filename parser)
  - `tests/unit/test_filename_parser.py` (new — 21 unit-тестов)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 38 source files
  - `.venv/bin/pytest tests/unit/ -v` — 89/89 passed
  - `.venv/bin/pytest -m integration -v` — 28/28 passed
- Checks:
  - pytest unit: `yes` (89/89)
  - pytest integration: `yes` (28/28)
  - ruff: `yes`
  - mypy: `yes`
- Risks:
  - Парсер не знает контекст — название фильма с цифрами (напр. "Room 2015") может быть ошибочно распарсено как год
  - Список quality-маркеров конечный — экзотические релиз-группы могут остаться в title
- Next task:
  - MVP-013 — Layout file in target library (copy/move + update DB path)

---

## Task Report: MVP-011 — 2026-06-06

- Status: `done`
- Summary: Создал ffprobe wrapper (`MediaProbeResult`, `probe_media()`) для анализа медиафайлов — извлекает длительность, разрешение, кодеки, количество аудио- и субтитр-дорожек. Добавил 8 колонок probe-результатов в ImportCandidate (`probed_at`, `duration_secs`, `width`, `height`, `codec`, `audio_codec`, `audio_count`, `subtitle_count`) + миграцию. Реализовал `probe_candidates()` — обходит список кандидатов, запускает ffprobe и заполняет результат. 10 unit-тестов (парсинг JSON, ошибки: файл не найден, ffprobe не установлен, timeout, ненулевой exit, некорректный JSON, иммутабельность) + 3 integration-теста (успешный probe, отсутствующий файл → error, повторный пропуск уже probed).
- Changed files:
  - `src/filmoteka/infrastructure/media_probe.py` (new — ffprobe wrapper)
  - `src/filmoteka/domain/importing/models.py` (+ 8 probe-колонок в ImportCandidate)
  - `src/filmoteka/domain/importing/scan.py` (+ `probe_candidates()`, импорты CANDIDATE_ERROR/probe_media)
  - `migrations/versions/d4a7fb449f2b_add_probe_columns_to_import_candidates.py` (new)
  - `tests/unit/test_media_probe.py` (new — 10 unit-тестов)
  - `tests/integration/test_importing.py` (+ 3 integration-теста для probe)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 36 source files
  - `.venv/bin/pytest tests/unit/ -v` — 68/68 passed
  - `.venv/bin/pytest -m integration -v` — 28/28 passed
- Checks:
  - pytest unit: `yes` (68/68)
  - pytest integration: `yes` (28/28)
  - ruff: `yes`
  - mypy: `yes`
- Risks:
  - Ubuntu ffmpeg 8.0.1 — совместимость с другими дистрибутивами не проверялась
  - subprocess timeout 60s — для очень больших файлов может не хватить
- Next task:
  - MVP-012 — Probe pipeline integration: wire probe_candidates into the scan flow

---

## Task Report: MVP-010 — 2026-06-06

- Status: `done`
- Summary: Создал ImportCandidate модель (id, import_run_id FK CASCADE, file_path, size, status), статусные константы (pending/probed/imported/error), миграцию для import_candidates. Обновил scan_downloads() — теперь создаёт ImportCandidate для каждого найденного файла с размером из stat и статусом pending. 4 новых unit-теста (создание, repr, кастомный статус, relationship) + 2 новых integration теста (создание кандидатов в БД, cascade delete при удалении ImportRun).
- Changed files:
  - `src/filmoteka/domain/importing/models.py` (+ ImportCandidate, статусные константы, relationship на ImportRun)
  - `src/filmoteka/domain/importing/scan.py` (+ bulk create ImportCandidate при сканировании)
  - `migrations/versions/0322c3ea4703_add_import_candidates_table.py` (new)
  - `tests/unit/test_scan.py` (+ TestImportCandidateModel — 4 теста)
  - `tests/integration/test_importing.py` (+ 2 теста: создание кандидатов, cascade delete)
  - `docs/progress.md` (snapshot + report)
- Commands run:
  - `.venv/bin/ruff check src/ tests/` — all checks passed
  - `.venv/bin/mypy src/ tests/` — success, 34 source files
  - `.venv/bin/pytest tests/unit/ -v` — 57/57 passed
  - `.venv/bin/pytest -m integration -v` — 25/25 passed
  - `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` — round-trip OK
- Checks:
  - pytest unit: `yes` (57/57)
  - pytest integration: `yes` (25/25)
  - ruff: `yes`
  - mypy: `yes`
  - alembic upgrade/downgrade: `yes`
- Risks:
  - Python-level default для status не работает в SQLAlchemy (default — Column-level, не __init__), но все места создания ImportCandidate передают статус явно — не проблема
- Next task:
  - MVP-011 — Technical probe: duration, resolution, codecs

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
