"""File layout — move scanned files into the target library directory."""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from filmoteka.domain.importing.models import (
    CANDIDATE_ERROR,
    CANDIDATE_IMPORTED,
    ImportCandidate,
)
from filmoteka.infrastructure.filename_parser import parse_filename
from filmoteka.infrastructure.library_config import LibraryConfig


class LayoutError(Exception):
    """Raised when a file cannot be laid out."""


def _target_dir(config: LibraryConfig, candidate: ImportCandidate) -> Path:
    """Determine the target directory for *candidate* based on its filename."""
    parsed = parse_filename(Path(candidate.file_path))
    title = parsed.title or "unknown"
    # Sanitise: keep only safe filename characters.
    safe_title = _sanitise(title)

    if parsed.year:
        dir_name = f"{safe_title} ({parsed.year})"
        return config.paths.target_root / str(parsed.year) / dir_name
    return config.paths.target_root / "unknown" / safe_title


def _sanitise(name: str) -> str:
    """Remove characters that are problematic in directory/file names."""
    return "".join(c for c in name if c.isprintable() and c not in r'<>:"/\|?*').strip()


def _unique_path(target: Path) -> Path:
    """If *target* already exists, append a numeric suffix.

    Returns a path that does not exist on disk yet.
    """
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    parent = target.parent

    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def layout_file(
    candidate: ImportCandidate,
    config: LibraryConfig,
    db: Session,
) -> None:
    """Move *candidate*'s file from downloads to the target library.

    The target path is built from the parsed filename::

        <target_root>/<year>/<title> (<year>)/<filename>

    If the year is unknown the file goes to ``unknown/<title>/``.

    Updates ``candidate.file_path`` and sets status to ``CANDIDATE_IMPORTED``.
    On failure sets status to ``CANDIDATE_ERROR`` and raises ``LayoutError``.
    """
    source = Path(candidate.file_path)
    if not source.is_file():
        candidate.status = CANDIDATE_ERROR
        db.flush()
        raise LayoutError(f"Source file does not exist: {source}")

    target_dir = _target_dir(config, candidate)
    dest = _unique_path(target_dir / source.name)

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(dest))
    except OSError as exc:
        candidate.status = CANDIDATE_ERROR
        db.flush()
        raise LayoutError(f"Failed to move {source} -> {dest}: {exc}") from exc

    candidate.file_path = str(dest)
    candidate.status = CANDIDATE_IMPORTED
    db.flush()
