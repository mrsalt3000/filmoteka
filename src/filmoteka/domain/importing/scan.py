"""Scan downloads directory for importable video files."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from filmoteka.domain.importing.models import ImportRun
from filmoteka.infrastructure.library_config import LibraryConfig


def scan_downloads(
    config: LibraryConfig,
    db: Session,
) -> ImportRun:
    """Scan ``config.paths.downloads_root`` and create an ``ImportRun``.

    Returns a persisted ``ImportRun`` with file_count set to the number of
    matching video files found.
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
    run.file_count = len(files)
    run.finished_at = datetime.now()
    run.status = "completed"
    db.flush()

    return run


def _collect_files(root: Path, extensions: list[str]) -> list[Path]:
    """Recursively collect files under *root* whose suffix is in *extensions*."""
    ext_set = {e.lower() for e in extensions}
    return sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in ext_set
    )
