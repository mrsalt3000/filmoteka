"""Import pipeline orchestrator — scan, probe, and bridge to catalog.

Files are indexed in-place: the library directory is scanned and catalog
entries are created without moving or copying any files.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from filmoteka.domain.catalog.models import (
    Film,
    Genre,
    MediaFile,
    MovieEdition,
    Person,
    film_person,
)
from filmoteka.domain.importing.models import (
    CANDIDATE_IMPORTED,
    CANDIDATE_PENDING,
    CANDIDATE_PROBED,
    ImportCandidate,
)
from filmoteka.domain.importing.scan import probe_candidates, scan_downloads
from filmoteka.infrastructure.deepseek_provider import (
    DeepSeekEnrichmentResult,
    deepseek_enrich_metadata,
)
from filmoteka.infrastructure.filename_parser import parse_filename
from filmoteka.infrastructure.library_config import LibraryConfig
from filmoteka.infrastructure.metadata_providers import omdb_search_poster
from filmoteka.infrastructure.settings import settings

_logger = logging.getLogger(__name__)


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

    # --- Metadata quality: initial from filename ---
    has_year = parsed.year is not None
    film.metadata_source = "filename_parse"
    film.metadata_confidence = 0.6 if has_year else 0.3
    film.metadata_enriched_at = None
    film.needs_review = False

    # --- Poster enrichment via OMDB (best-effort) ---
    poster_found = False
    if film.poster_url is None and settings.omdb_api_key:
        result = omdb_search_poster(parsed.title, parsed.year, settings.omdb_api_key)
        if result is not None:
            film.poster_url, film.poster_source = result
            poster_found = True

    # --- Metadata quality: upgrade if OMDB found a poster ---
    if settings.omdb_api_key:
        if poster_found:
            film.metadata_source = "omdb"
            film.metadata_confidence = 0.9
            film.metadata_enriched_at = datetime.now()
            film.needs_review = False
        else:
            film.needs_review = True

    # --- DeepSeek enrichment (best-effort) ---
    if settings.deepseek_api_key:
        deepseek_result = deepseek_enrich_metadata(
            parsed.title, parsed.year, settings.deepseek_api_key,
        )
        if deepseek_result is not None:
            _apply_deepseek_enrichment(film, deepseek_result, db)

    # --- MovieEdition ---
    edition = _find_or_create_edition(
        db,
        film.id,
        parsed.quality,
        parsed.language,
        parsed.edition_type,
    )

    # --- Conflict detection: edition already has media files ---
    if edition.id is not None:
        existing_count = db.query(MediaFile).filter(
            MediaFile.edition_id == edition.id
        ).count()
        if existing_count > 0:
            film.needs_review = True
            _logger.warning(
                "Potential duplicate for film %r — edition %d already has %d media file(s)",
                film.title, edition.id, existing_count,
            )

    # --- MediaFile ---
    existing_media = _find_media_by_path(db, candidate.file_path)
    if existing_media is not None:
        _logger.info("MediaFile already exists for path %s — skipping", candidate.file_path)
        return

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
    """Look up a Film by title (case-insensitive) and optional year.

    Title is normalised (stripped, whitespace collapsed) before matching.
    """
    norm = " ".join(title.split())
    query = db.query(Film).filter(Film.title.ilike(norm))
    if year is not None:
        query = query.filter(Film.year == year)
    else:
        query = query.filter(Film.year.is_(None))
    return query.first()


def _find_media_by_path(db: Session, file_path: str) -> MediaFile | None:
    """Look up a MediaFile by its ``file_path``."""
    return db.query(MediaFile).filter(MediaFile.file_path == file_path).first()


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
# DeepSeek enrichment helpers
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """Convert a genre name to a URL-friendly slug."""
    return text.lower().replace(" ", "-").replace("/", "-").replace("&", "and")


def _apply_deepseek_enrichment(
    film: Film,
    result: DeepSeekEnrichmentResult,
    db: Session,
) -> None:
    """Apply DeepSeek enrichment result to a Film entity.

    Updates description, country, genres, and actors.
    Sets metadata source to ``"deepseek"`` with confidence 0.9.
    """
    # Text fields
    if result.description:
        film.description = result.description
    if result.country:
        film.country = result.country

    # Genres — find or create by slug
    for name in result.genres:
        slug = _slugify(name)
        genre = db.query(Genre).filter(Genre.slug == slug).first()
        if genre is None:
            genre = Genre(name=name, slug=slug)
            db.add(genre)
            db.flush()
        if genre not in film.genres:
            film.genres.append(genre)

    # Actors — find or create by name with role "actor"
    for name in result.actors:
        person = db.query(Person).filter(Person.name == name).first()
        if person is None:
            person = Person(name=name)
            db.add(person)
            db.flush()
        # Check if already linked to avoid PK violation
        existing_link = db.execute(
            film_person.select().where(
                film_person.c.film_id == film.id,
                film_person.c.person_id == person.id,
            )
        ).first()
        if existing_link is None:
            db.execute(
                film_person.insert().values(
                    film_id=film.id, person_id=person.id, role="actor",
                )
            )

    # Metadata quality — DeepSeek enriches more than filename/OMDB
    film.metadata_source = "deepseek"
    film.metadata_confidence = 0.9
    film.metadata_enriched_at = datetime.now()
    film.needs_review = False


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
