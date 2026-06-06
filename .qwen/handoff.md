# Handoff — 2026-06-06

## Stopped at

- Phase: `mvp` — **50%**
- Last completed task: **MVP-010**
- Branch: `main` (up to date with `origin/main`), HEAD `5dbada9`
- 57 unit tests pass, 25 integration tests pass, ruff & mypy clean

## Changed files (this session)

```
src/filmoteka/domain/importing/models.py
src/filmoteka/domain/importing/scan.py
migrations/versions/0322c3ea4703_add_import_candidates_table.py
tests/unit/test_scan.py
tests/integration/test_importing.py
docs/progress.md
.qwen/handoff.md
```

## First things to verify on next run

1. `git status` — only `.qwen/settings.json` should be dirty
2. `.venv/bin/pytest tests/unit/ -v` — 57/57 passed
3. `.venv/bin/pytest -m integration -v` — 25/25 passed (requires `docker compose up -d db`)
4. `.venv/bin/ruff check src/ tests/` — all checks passed
5. `.venv/bin/mypy src/ tests/` — success

## Next recommended step

**MVP-011** — Technical probe: duration, resolution, codecs

- External CLI (ffprobe) wrapper for media file analysis
- Update ImportCandidate or media_file schema with probe results
- Store probe data (duration, resolution, codecs, subtitle/audio count)
- Unit + integration tests
