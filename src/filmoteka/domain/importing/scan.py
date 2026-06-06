"""Scan downloads directory for importable video files."""

from __future__ import annotations

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


def scan_downloads(
    config: LibraryConfig,
    db: Session,
) -> ImportRun:
    """Scan ``config.paths.downloads_root`` and create an ``ImportRun``.

    Returns a persisted ``ImportRun`` with file_count set to the number of
    matching video files found, each represented as an ``ImportCandidate``.
    """
    root = config.paths.downloads_root
    extensions = config.import_.extensions

    if not root.is_dir():
        raise NotADirectoryError(
            f"Downloads root does not exist or is not a directory: {root}"
        )

    run = ImportRun(status="running")
    db.add(run)
    db.flush()  # get an id

    files = _collect_files(root, extensions)
    candidates = [
        ImportCandidate(
            import_run_id=run.id,
            file_path=str(f),
            size=f.stat().st_size,
            status=CANDIDATE_PENDING,
        )
        for f in files
    ]
    db.add_all(candidates)
    run.file_count = len(files)
    run.finished_at = datetime.now()
    run.status = "completed"
    db.flush()

    return run


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
    """Recursively collect files under *root* whose suffix is in *extensions*."""
    ext_set = {e.lower() for e in extensions}
    return sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in ext_set
    )
