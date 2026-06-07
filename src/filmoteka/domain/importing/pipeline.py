"""Import pipeline orchestrator — scan, probe, layout, and bridge to catalog."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from filmoteka.domain.catalog.models import Film, MediaFile, MovieEdition
from filmoteka.domain.importing.layout import layout_file
from filmoteka.domain.importing.models import (
    CANDIDATE_IMPORTED,
    CANDIDATE_PROBED,
    ImportCandidate,
)
from filmoteka.domain.importing.scan import probe_candidates, scan_downloads
from filmoteka.infrastructure.filename_parser import parse_filename
from filmoteka.infrastructure.library_config import LibraryConfig


def run_import(config: LibraryConfig, db: Session) -> ImportReport:
    """Run the full import pipeline: scan → probe → layout → bridge.

    Returns an ``ImportReport`` summarising what happened.
    """
    # 1. Scan — discover new files
    run = scan_downloads(config, db)
    db.refresh(run)

    report = ImportReport(
        files_found=run.file_count,
        files_probed=0,
        files_laid_out=0,
        films_created=0,
        films_skipped=0,
        errors=[],
    )

    candidates: list[ImportCandidate] = (
        db.query(ImportCandidate)
        .filter(ImportCandidate.import_run_id == run.id)
        .all()
    )

    if not candidates:
        return report

    # 2. Probe — run ffprobe on all pending candidates
    probe_candidates(candidates, db)
    for c in candidates:
        db.refresh(c)

    probed = [c for c in candidates if c.status == CANDIDATE_PROBED]
    report.files_probed = len(probed)

    if not probed:
        return report

    # 3. Layout — move each probed file to the target library
    for c in probed:
        try:
            layout_file(c, config, db)
        except Exception as exc:
            report.errors.append(f"layout failed for {c.file_path}: {exc}")
            continue

    db.flush()

    # 4. Bridge — create catalog entries for successfully laid-out files
    imported = (
        db.query(ImportCandidate)
        .filter(
            ImportCandidate.import_run_id == run.id,
            ImportCandidate.status == CANDIDATE_IMPORTED,
        )
        .all()
    )
    report.files_laid_out = len(imported)

    for c in imported:
        try:
            _bridge_to_catalog(c, db)
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

    # --- MovieEdition ---
    edition = _find_or_create_edition(db, film.id, parsed.quality)

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
) -> MovieEdition:
    """Find existing ``MovieEdition`` or create a new one."""
    if quality is not None:
        existing = (
            db.query(MovieEdition)
            .filter(
                MovieEdition.film_id == film_id,
                MovieEdition.quality == quality,
            )
            .first()
        )
    else:
        existing = (
            db.query(MovieEdition)
            .filter(
                MovieEdition.film_id == film_id,
                MovieEdition.quality.is_(None),
            )
            .first()
    )
    if existing is not None:
        return existing

    edition = MovieEdition(
        film_id=film_id,
        quality=quality,
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
        files_laid_out: int = 0,
        films_created: int = 0,
        films_skipped: int = 0,
        errors: list[str] | None = None,
    ) -> None:
        self.files_found = files_found
        self.files_probed = files_probed
        self.files_laid_out = files_laid_out
        self.films_created = films_created
        self.films_skipped = films_skipped
        self.errors = errors or []

    def to_dict(self) -> dict[str, object]:
        return {
            "files_found": self.files_found,
            "files_probed": self.files_probed,
            "files_laid_out": self.files_laid_out,
            "films_created": self.films_created,
            "films_skipped": self.films_skipped,
            "errors": self.errors,
        }
