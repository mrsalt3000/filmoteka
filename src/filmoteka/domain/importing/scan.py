"""Scan downloads directory for importable video files."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from filmoteka.domain.importing.models import (
    CANDIDATE_ERROR,
    CANDIDATE_PENDING,
    CANDIDATE_PROBED,
    ImportCandidate,
    ImportRun,
)
from filmoteka.infrastructure.library_config import LibraryConfig
from filmoteka.infrastructure.media_probe import (
    MediaProbeError,
    probe_media,
)

_logger = logging.getLogger(__name__)


def scan_downloads(
    config: LibraryConfig,
    db: Session,
) -> ImportRun:
    """Scan ``config.paths.target_root`` and create an ``ImportRun``.

    Files are indexed in-place — no file copying occurs during import.
    Idempotent: files that already have an ``ImportCandidate`` with a
    non-error status are skipped so repeated scans do not create duplicates.

    Returns a persisted ``ImportRun`` with file_count set to the number of
    new candidates created.
    """
    root = config.paths.target_root
    extensions = config.import_.extensions

    if not root.is_dir():
        raise NotADirectoryError(
            f"Downloads root does not exist or is not a directory: {root}"
        )

    run = ImportRun(status="running")
    db.add(run)
    db.flush()  # get an id

    files = _collect_files(root, extensions)
    existing = _existing_candidate_paths(db, root, skip_status=CANDIDATE_ERROR)
    new_files = [f for f in files if str(f) not in existing]

    # Enforce max file size
    max_bytes = config.import_.max_file_size_gb * 1024**3
    oversized = [f for f in new_files if f.stat().st_size > max_bytes]
    for f in oversized:
        _logger.warning("Skipping oversized file (%d GB > %d GB): %s",
                        f.stat().st_size / 1024**3,
                        config.import_.max_file_size_gb, f)
    filtered = [f for f in new_files if f.stat().st_size <= max_bytes]

    candidates = [
        ImportCandidate(
            import_run_id=run.id,
            file_path=str(f),
            size=f.stat().st_size,
            status=CANDIDATE_PENDING,
        )
        for f in filtered
    ]
    db.add_all(candidates)
    run.file_count = len(filtered)
    run.finished_at = datetime.now()
    run.status = "completed"
    db.flush()

    return run


def _existing_candidate_paths(
    db: Session,
    root: Path,
    skip_status: str | None = None,
) -> set[str]:
    """Return file paths from the DB that are under *root*.

    If *skip_status* is set, candidates with that status are excluded from
    the result (so they can be re-scanned).
    """
    query = db.query(ImportCandidate.file_path).filter(
        ImportCandidate.file_path.startswith(str(root))
    )
    if skip_status:
        query = query.filter(ImportCandidate.status != skip_status)
    return {row[0] for row in query.all()}


def probe_candidates(
    candidates: list[ImportCandidate],
    db: Session,
) -> None:
    """Run ffprobe on each pending candidate and store results.

    Candidates that probe successfully are set to ``CANDIDATE_PROBED``.
    Candidates that fail get status ``CANDIDATE_ERROR``.
    """
    for candidate in candidates:
        if candidate.status != CANDIDATE_PENDING:
            continue

        path = Path(candidate.file_path)
        try:
            result = probe_media(path)
        except MediaProbeError:
            candidate.status = CANDIDATE_ERROR
            db.flush()
            continue

        candidate.probed_at = datetime.now()
        candidate.duration_secs = result.duration_secs
        candidate.width = result.width
        candidate.height = result.height
        candidate.codec = result.codec
        candidate.audio_codec = result.audio_codec
        candidate.audio_count = result.audio_count
        candidate.subtitle_count = result.subtitle_count
        candidate.status = CANDIDATE_PROBED
        db.flush()


def _collect_files(root: Path, extensions: list[str]) -> list[Path]:
    """Recursively collect files under *root* whose suffix is in *extensions*.

    Directories named ``transcoded`` are skipped — they contain
    previously transcoded media and must not be re-imported.
    """
    ext_set = {e.lower() for e in extensions}
    return sorted(
        p for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in ext_set
        and "transcoded" not in p.relative_to(root).parts
    )
