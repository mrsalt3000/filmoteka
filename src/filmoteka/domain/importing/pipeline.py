"""Import pipeline orchestrator — scan, probe, and bridge to catalog.

Files are indexed in-place: the library directory is scanned and catalog
entries are created without moving or copying any files.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy.orm import Session

from filmoteka.domain.catalog.models import Film, MediaFile, MovieEdition
from filmoteka.domain.importing.models import (
    CANDIDATE_IMPORTED,
    CANDIDATE_PENDING,
    CANDIDATE_PROBED,
    ImportCandidate,
)
from filmoteka.domain.importing.scan import probe_candidates, scan_downloads
from filmoteka.infrastructure.filename_parser import parse_filename
from filmoteka.infrastructure.library_config import LibraryConfig
from filmoteka.infrastructure.metadata_providers import tmdb_search_poster
from filmoteka.infrastructure.settings import settings


def _ffprobe_available() -> bool:
    """Return ``True`` if ``ffprobe`` is found on ``PATH``."""
    return shutil.which("ffprobe") is not None


def run_import(config: LibraryConfig, db: Session) -> ImportReport:
    """Run the import pipeline: scan → probe → bridge (no file copying).

    Files are indexed in-place from ``config.paths.target_root``.
    Catalog entries (Film, MovieEdition, MediaFile) are created directly.
    """
    # 1. Scan — discover new files in the library directory
    run = scan_downloads(config, db)
    db.refresh(run)

    report = ImportReport(
        files_found=run.file_count,
    )

    candidates: list[ImportCandidate] = (
        db.query(ImportCandidate)
        .filter(ImportCandidate.import_run_id == run.id)
        .all()
    )

    if not candidates:
        return report

    # 2. Probe — run ffprobe on all pending candidates (best-effort).
    # If ffprobe is not available (e.g. Windows without ffmpeg), skip.
    if _ffprobe_available():
        probe_candidates(candidates, db)
        for c in candidates:
            db.refresh(c)

    probed = [c for c in candidates if c.status == CANDIDATE_PROBED]
    report.files_probed = len(probed)

    # Candidates to bridge: probed ones, or pending ones if probe didn't run.
    to_bridge = probed or [c for c in candidates if c.status == CANDIDATE_PENDING]

    # 3. Bridge — create catalog entries directly (no file copy).
    for c in to_bridge:
        try:
            _bridge_to_catalog(c, db)
            c.status = CANDIDATE_IMPORTED
            report.files_indexed += 1
            report.films_created += 1
        except Exception as exc:
            report.errors.append(f"bridge failed for {c.file_path}: {exc}")
            continue

    db.commit()
    return report


def _bridge_to_catalog(candidate: ImportCandidate, db: Session) -> None:
    """Create or update catalog entries (Film, MovieEdition, MediaFile).

    Deduplication strategy:
    - Film is matched by title (case-insensitive) + year (nullable).
      If a matching film exists it is reused.
    - MovieEdition is matched by film_id + quality (nullable).
      If a matching edition exists it is reused.
    - MediaFile is matched by file_path (unique) — always created.
    """
    parsed = parse_filename(Path(candidate.file_path))

    # --- Film ---
    existing_film = _find_film(db, parsed.title, parsed.year)
    if existing_film is not None:
        film = existing_film
    else:
        film = Film(
            title=parsed.title,
            year=parsed.year,
        )
        db.add(film)
        db.flush()

    # --- Poster enrichment (best-effort) ---
    if film.poster_url is None and settings.tmdb_api_key:
        result = tmdb_search_poster(parsed.title, parsed.year, settings.tmdb_api_key)
        if result is not None:
            film.poster_url, film.poster_source = result

    # --- MovieEdition ---
    edition = _find_or_create_edition(
        db,
        film.id,
        parsed.quality,
        parsed.language,
        parsed.edition_type,
    )

    # --- MediaFile ---
    media = MediaFile(
        edition_id=edition.id,
        file_path=candidate.file_path,
        file_size=candidate.size,
        duration_secs=candidate.duration_secs,
        width=candidate.width,
        height=candidate.height,
        codec=candidate.codec,
        audio_codec=candidate.audio_codec,
    )
    db.add(media)
    db.flush()


def _find_film(db: Session, title: str, year: int | None) -> Film | None:
    """Look up a Film by title (case-insensitive) and optional year."""
    query = db.query(Film).filter(Film.title.ilike(title))
    if year is not None:
        query = query.filter(Film.year == year)
    else:
        query = query.filter(Film.year.is_(None))
    return query.first()


def _find_or_create_edition(
    db: Session,
    film_id: int,
    quality: str | None,
    language: str | None = None,
    edition_name: str | None = None,
) -> MovieEdition:
    """Find existing ``MovieEdition`` or create a new one.

    Dedup matches on ``film_id + quality + edition_name + language``.
    """
    query = db.query(MovieEdition).filter(
        MovieEdition.film_id == film_id,
        MovieEdition.quality == quality,
        MovieEdition.edition_name == edition_name,
        MovieEdition.language == language,
    )
    existing = query.first()
    if existing is not None:
        return existing

    edition = MovieEdition(
        film_id=film_id,
        quality=quality,
        edition_name=edition_name,
        language=language,
    )
    db.add(edition)
    db.flush()
    return edition


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class ImportReport:
    """Summary of an import pipeline run."""

    def __init__(
        self,
        files_found: int = 0,
        files_probed: int = 0,
        files_indexed: int = 0,
        films_created: int = 0,
        errors: list[str] | None = None,
    ) -> None:
        self.files_found = files_found
        self.files_probed = files_probed
        self.files_indexed = files_indexed
        self.films_created = films_created
        self.errors = errors or []

    def to_dict(self) -> dict[str, object]:
        return {
            "files_found": self.files_found,
            "files_probed": self.files_probed,
            "files_indexed": self.files_indexed,
            "films_created": self.films_created,
            "errors": self.errors,
        }
