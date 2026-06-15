# Handoff — 2026-06-15 (tenth session)

## Stopped at

- Phase: TV Series in full swing (SERIES-003 through SERIES-006), transcode fix (BUGFIX-009), BUGFIX-027 planned.
- Git: `89f63e8` — clean upstream, working tree has only local artifacts (`.qwen/skills/`, `.coverage`, deleted `tests/conftest.py`, deleted `docs/agent-tasklist.md`).
- Last commit: `89f63e8` — `feat: add series detail page with season tabs and episode Play buttons`

## Completed this session (6 commits, 5 tasks)

### BUGFIX-009 — Transcode & web-optimize
- **Проблема:** `empty_moov` в ffmpeg-ремуксе не давал браузеру узнать длительность → прогресс-бар ~10 сек. Транскодирование AC3→AAC в `.tr.mkv` не помогало, т.к. `.tr.mkv` всё равно шёл через тот же ремукс.
- **Решение:** двухшаговый pipeline: AC3→AAC → `.tr.mkv`, затем `ffmpeg -c copy -movflags +faststart` → `.tr.mp4`. После шага 2 `.tr.mkv` удаляется, `file_path` = `.tr.mp4`. Файл отдаётся через `FileResponse` с `Content-Length` + range support.
- **Cleanup:** `scripts/cleanup_tr.py` — 7 файлов восстановлены на оригиналы, 44 переименованы `.tr.mkv` → `.mkv`, 5 осиротевших оставлены. `audio_codec` сброшен в NULL.
- Files: `admin.py`, `index.html`, `scripts/cleanup_tr.py`

### SERIES-003 — Pipeline grouping
- `_bridge_to_catalog()`: при `parsed.series_title` → find-or-create Series, dedup по `series_id+season+episode`, заполняет поля Film. Хелпер `_find_or_create_series()`.
- 4 integration tests.
- Files: `pipeline.py`, `test_importing.py`

### SERIES-004 — Series API
- `GET /series` (list with episode_count via subquery), `GET /series/{id}` (detail with seasons grouped), `GET /series/{id}/episodes?season=N` (paginated).
- 9 integration tests.
- Files: `api/series.py` (new), `schemas/catalog.py`, `app.py`, `test_catalog.py`

### SERIES-005 — Series cards on main page
- `renderList()`: fetches `/series`, filters out episodes (`series_id == null`), renders series cards with poster + episode count badge. Click → `#series/{id}`.
- Files: `index.html`

### SERIES-006 — Series detail page
- `#series/{id}`: poster, season tabs (switch inline), episode list with Play button. `EpisodeOut` gains `media_id`.
- Files: `series.py`, `schemas/catalog.py`, `index.html`, `test_catalog.py`

## Changed files (this session)

```
agent-tasklist.md                                         # +BUGFIX-027, SERIES-003/004/005/006 [x]
docs/progress.md                                          # all task reports
scripts/cleanup_tr.py                                     # one-off cleanup script (new)
src/filmoteka/domain/importing/pipeline.py                # +Series grouping in bridge
src/filmoteka/api/series.py                               # new — 3 endpoints (new)
src/filmoteka/api/schemas/catalog.py                      # +series schemas, +media_id
src/filmoteka/app.py                                      # +series_router
src/filmoteka/api/admin.py                                # +web-optimize step in transcode
src/filmoteka/static/index.html                           # +series cards, +series page, CSS
tests/integration/test_importing.py                       # +4 series pipeline tests
tests/integration/test_catalog.py                         # +9 series API tests, media_id check
```

## Known open issues

1. **TV Series incomplete** — SERIES-007 (prev/next in player), SERIES-008 (series continue) remain.
2. **Pre-existing test failures** — ~27 integration tests fail when OMDB_API_KEY is set (host env triggers real OMDB calls). `test_health.py` fixture error (`conftest.py` deleted from git).
3. **BUGFIX-027** — ffmpeg remux fallback (`empty_moov`/`delay_moov`) planned for removal after all files are transcoded. Task exists in tasklist.
4. **BUGFIX-011, 012, 015** — Done but still marked `[ ]` in tasklist. Can be bulk-closed.
5. **V1-007** — Enrichment pipeline tests not written.

## First things to verify on next run

1. `docker compose build api && docker compose up -d api` — rebuild with new code
2. Re-scan library — verify series grouping: check `series_id`, `season_number`, `episode_number` in `GET /films/{id}` for episode files
3. Check `GET /series` returns list with episode_count
4. Open `#series/1` in browser — verify poster, season tabs, episode list with Play button
5. Click Play on an episode — verify it goes to player
6. Check `#list` — verify series cards appear instead of 90 individual episode cards
7. Run **Transcode & web-optimize** button — verify `.tr.mp4` is created, `.tr.mkv` is deleted
8. Open player for a `.tr.mp4` file — verify full duration and seeking

## Next recommended task

**SERIES-007** — Кнопки prev/next в плеере. При просмотре эпизода показывать кнопки для переключения на предыдущий/следующий эпизод того же сериала. Потребуется небольшой API-эндпойнт для получения соседних эпизодов по `media_id` + фронтенд-кнопки в `renderPlayer()`.
