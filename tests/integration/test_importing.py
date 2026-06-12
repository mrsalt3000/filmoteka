"""Integration tests for the import pipeline."""

from __future__ import annotations

import subprocess
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from filmoteka.domain.importing.layout import layout_file
from filmoteka.domain.importing.models import (
    CANDIDATE_ERROR,
    CANDIDATE_IMPORTED,
    CANDIDATE_PENDING,
    CANDIDATE_PROBED,
    ImportCandidate,
    ImportRun,
)
from filmoteka.domain.importing.scan import probe_candidates, scan_downloads
from filmoteka.infrastructure.library_config import LibraryConfig
from filmoteka.infrastructure.settings import settings

pytestmark = pytest.mark.integration


def _make_config(
    root: Path,
) -> LibraryConfig:
    return LibraryConfig.model_validate({
        "paths": {
            "downloads_root": str(root),
            "target_root": str(root),
        },
        "import": {"extensions": [".mp4", ".mkv"], "max_file_size_gb": 50},
        "organization": "by_year",
    })


def _make_test_video(path: Path) -> None:
    """Generate a tiny valid MP4 with one video + one audio stream."""
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f", "lavfi",
            "-i", "testsrc=duration=1:size=32x24:rate=1",
            "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=mono",
            "-shortest",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )


class TestScanDownloads:
    """scan_downloads — end-to-end with real DB."""

    def test_scan_creates_import_run(self, db_session: Session, tmp_path: Path) -> None:
        (tmp_path / "film.mp4").touch()
        (tmp_path / "series.mkv").touch()

        config = _make_config(tmp_path)
        run = scan_downloads(config, db_session)

        assert isinstance(run, ImportRun)
        assert run.id is not None
        assert run.status == "completed"
        assert run.file_count == 2
        assert run.finished_at is not None

    def test_scan_no_files(self, db_session: Session, tmp_path: Path) -> None:
        config = _make_config(tmp_path)
        run = scan_downloads(config, db_session)
        assert run.file_count == 0
        assert run.status == "completed"

    def test_scan_nonexistent_directory(
        self, db_session: Session
    ) -> None:
        config = _make_config(Path("/does/not/exist"))
        with pytest.raises(NotADirectoryError):
            scan_downloads(config, db_session)

    def test_scan_creates_candidates(self, db_session: Session, tmp_path: Path) -> None:
        (tmp_path / "film.mp4").write_bytes(b"x" * 100)
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.mkv").write_bytes(b"x" * 200)

        config = _make_config(tmp_path)
        run = scan_downloads(config, db_session)
        db_session.refresh(run)

        candidates = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .order_by(ImportCandidate.file_path)
            .all()
        )

        assert len(candidates) == 2
        assert candidates[0].file_path == str(tmp_path / "film.mp4")
        assert candidates[0].size == 100
        assert candidates[0].status == "pending"
        assert candidates[1].file_path == str(tmp_path / "subdir" / "nested.mkv")
        assert candidates[1].size == 200
        assert candidates[1].import_run_id == run.id


class TestScanIdempotent:
    """scan_downloads — repeated calls must not create duplicates."""

    def test_second_scan_creates_no_new_candidates(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        (tmp_path / "film.mp4").touch()
        config = _make_config(tmp_path)

        # First scan
        run1 = scan_downloads(config, db_session)
        assert run1.file_count == 1

        # Second scan — same files, should find nothing new
        run2 = scan_downloads(config, db_session)
        assert run2.file_count == 0

        # Total candidates should still be 1
        total = (
            db_session.query(ImportCandidate)
            .count()
        )
        assert total == 1

    def test_scan_after_error_allows_retry(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        video = tmp_path / "film.mp4"
        video.touch()
        config = _make_config(tmp_path)

        # First scan
        run1 = scan_downloads(config, db_session)
        # Manually set candidate to error
        c = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run1.id)
            .one()
        )
        c.status = CANDIDATE_ERROR
        db_session.flush()

        # Second scan — file is still there, status was error → should re-create
        run2 = scan_downloads(config, db_session)
        assert run2.file_count == 1

        total = (
            db_session.query(ImportCandidate)
            .count()
        )
        # Original + new = 2 (new run, new candidate)
        assert total == 2

    def test_scan_partial_new_files(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        (tmp_path / "existing.mp4").touch()
        config = _make_config(tmp_path)

        run1 = scan_downloads(config, db_session)
        assert run1.file_count == 1

        # Add a new file
        (tmp_path / "new_film.mkv").touch()

        run2 = scan_downloads(config, db_session)
        assert run2.file_count == 1  # only the new file

        total = (
            db_session.query(ImportCandidate)
            .count()
        )
        assert total == 2  # 1 from first run + 1 from second


class TestProbeCandidates:
    """probe_candidates — end-to-end with real DB and real media file."""

    def test_probe_success(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        (tmp_path / "film.mp4").touch()
        config = _make_config(tmp_path)
        run = scan_downloads(config, db_session)
        db_session.refresh(run)

        candidates = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .all()
        )
        assert len(candidates) == 1

        # Replace the empty file with a real video
        _make_test_video(Path(candidates[0].file_path))

        probe_candidates(candidates, db_session)
        db_session.refresh(candidates[0])

        c = candidates[0]
        assert c.status == CANDIDATE_PROBED
        assert c.probed_at is not None
        assert c.codec is not None
        assert c.width is not None and c.width > 0
        assert c.height is not None and c.height > 0
        assert c.audio_codec is not None

    def test_probe_missing_file(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        (tmp_path / "film.mp4").touch()
        config = _make_config(tmp_path)
        run = scan_downloads(config, db_session)
        db_session.refresh(run)

        candidates = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .all()
        )

        # Delete the file so probe fails
        Path(candidates[0].file_path).unlink()

        probe_candidates(candidates, db_session)
        db_session.refresh(candidates[0])

        assert candidates[0].status == CANDIDATE_ERROR
        assert candidates[0].probed_at is None

    def test_probe_skips_already_probed(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        (tmp_path / "film.mp4").touch()
        config = _make_config(tmp_path)
        run = scan_downloads(config, db_session)
        db_session.refresh(run)

        candidates = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .all()
        )
        _make_test_video(Path(candidates[0].file_path))

        # First probe — should succeed
        probe_candidates(candidates, db_session)
        db_session.refresh(candidates[0])
        assert candidates[0].status == CANDIDATE_PROBED
        first_probed_at = candidates[0].probed_at

        # Second probe — should skip because status is already probed
        probe_candidates(candidates, db_session)
        db_session.refresh(candidates[0])
        assert candidates[0].probed_at == first_probed_at


class TestCandidateCascadeDelete:
    """Cascade delete of ImportCandidate when ImportRun is removed."""

    def test_candidate_cascade_delete(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        (tmp_path / "film.mp4").touch()
        config = _make_config(tmp_path)
        run = scan_downloads(config, db_session)

        candidates_before = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .count()
        )
        assert candidates_before == 1

        db_session.delete(run)
        db_session.flush()

        candidates_after = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .count()
        )
        assert candidates_after == 0


class TestLayoutFile:
    """layout_file — move file within the library directory."""

    def test_move_file_with_year(self, db_session: Session, tmp_path: Path) -> None:
        root = tmp_path

        video = root / "The.Matrix.1999.1080p.mkv"
        video.write_text("fake video content")

        config = _make_config(root)
        run = scan_downloads(config, db_session)
        db_session.refresh(run)

        candidates = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .all()
        )
        assert len(candidates) == 1
        c = candidates[0]

        layout_file(c, config, db_session)
        db_session.refresh(c)

        assert c.status == CANDIDATE_IMPORTED
        # File should no longer be at source
        assert not video.exists()
        # File should be at the new path
        new_path = Path(c.file_path)
        assert new_path.exists()
        assert new_path.read_text() == "fake video content"
        # Path should follow the year layout
        assert "1999" in new_path.parts
        assert "The Matrix (1999)" in new_path.parts

    def test_move_file_without_year(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        root = tmp_path

        video = root / "Some Movie.mkv"
        video.write_text("content")

        config = _make_config(root)
        run = scan_downloads(config, db_session)
        db_session.refresh(run)

        candidates = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .all()
        )
        c = candidates[0]

        layout_file(c, config, db_session)
        db_session.refresh(c)

        assert c.status == CANDIDATE_IMPORTED
        new_path = Path(c.file_path)
        assert new_path.exists()
        assert "unknown" in new_path.parts

    def test_move_updates_db_path(self, db_session: Session, tmp_path: Path) -> None:
        root = tmp_path
        (root / "Avatar.2009.2160p.mkv").write_text("data")

        config = _make_config(root)
        run = scan_downloads(config, db_session)
        db_session.refresh(run)

        c = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .one()
        )
        old_path = c.file_path

        layout_file(c, config, db_session)
        db_session.refresh(c)

        assert c.file_path != old_path
        # DB path should be absolute and point to an existing file
        assert Path(c.file_path).exists()


class TestFullPipeline:
    """End-to-end import pipeline: scan → probe → layout with real file (old workflow)."""

    def test_scan_probe_layout_flow(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        root = tmp_path

        video = root / "The.Matrix.1999.1080p.mkv"
        _make_test_video(video)

        config = _make_config(root)

        # 1. Scan
        run = scan_downloads(config, db_session)
        assert run.file_count == 1

        candidates = (
            db_session.query(ImportCandidate)
            .filter(ImportCandidate.import_run_id == run.id)
            .all()
        )
        assert len(candidates) == 1
        assert candidates[0].status == CANDIDATE_PENDING

        # 2. Probe
        probe_candidates(candidates, db_session)
        db_session.refresh(candidates[0])
        assert candidates[0].status == CANDIDATE_PROBED
        assert candidates[0].width is not None
        assert candidates[0].duration_secs is not None

        # 3. Layout
        layout_file(candidates[0], config, db_session)
        db_session.refresh(candidates[0])
        assert candidates[0].status == CANDIDATE_IMPORTED

        # Source file should be gone
        assert not video.exists()
        # Target file should exist with probe data preserved
        final = Path(candidates[0].file_path)
        assert final.exists()
        assert "The Matrix (1999)" in final.parts
        assert final.suffix == ".mkv"


class TestPipelineBridge:
    """End-to-end import pipeline (index-only): scan → probe → bridge."""

    @pytest.fixture(autouse=True)
    def _mock_deepseek(self) -> Generator[None, None, None]:
        """Prevent DeepSeek API calls during import pipeline tests."""
        with patch(
            "filmoteka.domain.importing.pipeline.deepseek_enrich_metadata",
            return_value=None,
        ):
            yield

    def test_full_pipeline_creates_film(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        from filmoteka.domain.catalog.models import Film, MediaFile, MovieEdition
        from filmoteka.domain.importing.pipeline import run_import

        root = tmp_path

        video = root / "The.Matrix.1999.1080p.mkv"
        _make_test_video(video)

        config = _make_config(root)

        report = run_import(config, db_session)

        assert report.files_found == 1
        assert report.files_probed == 1
        assert report.files_indexed == 1
        assert report.films_created == 1
        assert report.errors == []

        # File stays in place (no copy)
        assert video.exists()

        films = db_session.query(Film).all()
        assert len(films) == 1
        assert films[0].title == "The Matrix"
        assert films[0].year == 1999

        editions = db_session.query(MovieEdition).all()
        assert len(editions) == 1
        assert editions[0].film_id == films[0].id

        media_files = db_session.query(MediaFile).all()
        assert len(media_files) == 1
        assert media_files[0].edition_id == editions[0].id
        assert Path(media_files[0].file_path).exists()
        # Probe data is present when ffprobe is available
        assert media_files[0].duration_secs is not None
        assert media_files[0].width is not None

        # Poster enrichment gracefully skipped (no OMDB_API_KEY in tests by default)
        assert films[0].poster_url is None
        assert films[0].poster_source is None

        # Metadata quality fields — no OMDB_API_KEY in default test env,
        # so enrichment is skipped and needs_review stays False.
        assert films[0].metadata_source == "filename_parse"
        assert films[0].metadata_confidence == 0.6  # title + year
        assert films[0].metadata_enriched_at is None
        assert films[0].needs_review is False

    def test_pipeline_dedup_skips_existing_film(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        from filmoteka.domain.catalog.models import Film
        from filmoteka.domain.importing.pipeline import run_import

        root = tmp_path

        video = root / "The.Matrix.1999.1080p.mkv"
        _make_test_video(video)

        config = _make_config(root)

        run1 = run_import(config, db_session)
        assert run1.films_created == 1
        assert run1.files_found == 1

        run2 = run_import(config, db_session)
        assert run2.files_found == 0

        films = db_session.query(Film).all()
        assert len(films) == 1

    def test_pipeline_without_year_creates_film(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        from filmoteka.domain.catalog.models import Film
        from filmoteka.domain.importing.pipeline import run_import

        root = tmp_path

        video = root / "Some Movie.mkv"
        _make_test_video(video)

        config = _make_config(root)

        report = run_import(config, db_session)

        assert report.films_created == 1
        film = db_session.query(Film).one()
        assert film.title == "Some Movie"
        assert film.year is None

        # Metadata quality: no year → lower confidence; no OMDB_API_KEY in
        # default test env, so enrichment is skipped.
        assert film.metadata_source == "filename_parse"
        assert film.metadata_confidence == 0.3  # title only, no year
        assert film.metadata_enriched_at is None
        assert film.needs_review is False

    # ── Quality flags: OMDB enrichment ────────────────────────────

    @patch.object(settings, "omdb_api_key", "test_key")
    @patch("filmoteka.domain.importing.pipeline.omdb_search_poster")
    def test_bridge_omdb_success_upgrades_quality(
        self,
        mock_poster: object,
        db_session: Session,
        tmp_path: Path,
    ) -> None:
        """When OMDB finds a poster, quality is upgraded."""
        from filmoteka.domain.catalog.models import Film
        from filmoteka.domain.importing.pipeline import run_import

        mock_poster.return_value = ("http://img/poster.jpg", "omdb")  # type: ignore[attr-defined]

        root = tmp_path
        video = root / "The.Matrix.1999.1080p.mkv"
        _make_test_video(video)
        config = _make_config(root)

        run_import(config, db_session)

        film = db_session.query(Film).one()
        assert film.metadata_source == "omdb"
        assert film.metadata_confidence == 0.9
        assert film.metadata_enriched_at is not None
        assert film.needs_review is False
        assert film.poster_url == "http://img/poster.jpg"

    @patch.object(settings, "omdb_api_key", "test_key")
    @patch("filmoteka.domain.importing.pipeline.omdb_search_poster")
    def test_bridge_omdb_empty_sets_needs_review(
        self,
        mock_poster: object,
        db_session: Session,
        tmp_path: Path,
    ) -> None:
        """When OMDB is reachable but returns nothing, needs_review=True."""
        from filmoteka.domain.catalog.models import Film
        from filmoteka.domain.importing.pipeline import run_import

        mock_poster.return_value = None  # type: ignore[attr-defined]

        root = tmp_path
        video = root / "The.Matrix.1999.1080p.mkv"
        _make_test_video(video)
        config = _make_config(root)

        run_import(config, db_session)

        film = db_session.query(Film).one()
        assert film.metadata_source == "filename_parse"
        assert film.metadata_confidence == 0.6
        assert film.metadata_enriched_at is None
        assert film.needs_review is True
        assert film.poster_url is None

    @patch.object(settings, "omdb_api_key", None)
    def test_bridge_without_omdb_key_keeps_filename_level(
        self,
        db_session: Session,
        tmp_path: Path,
    ) -> None:
        """Without OMDB_API_KEY, quality stays at filename_parse level."""
        from filmoteka.domain.catalog.models import Film
        from filmoteka.domain.importing.pipeline import run_import

        root = tmp_path
        video = root / "The.Matrix.1999.1080p.mkv"
        _make_test_video(video)
        config = _make_config(root)

        run_import(config, db_session)

        film = db_session.query(Film).one()
        assert film.metadata_source == "filename_parse"
        assert film.metadata_confidence == 0.6
        assert film.needs_review is False  # no OMDB key → no reason to flag
        assert film.poster_url is None

    # ── Dedup: film and edition matching ───────────────────────────

    def test_bridge_two_files_same_film_different_quality(
        self,
        db_session: Session,
        tmp_path: Path,
    ) -> None:
        """Two files with the same title+year but different quality → one film, two editions."""
        from filmoteka.domain.catalog.models import Film, MediaFile, MovieEdition
        from filmoteka.domain.importing.pipeline import run_import

        root = tmp_path
        v1 = root / "The.Matrix.1999.1080p.mkv"
        v2 = root / "The.Matrix.1999.2160p.mkv"
        _make_test_video(v1)
        _make_test_video(v2)
        config = _make_config(root)

        run_import(config, db_session)

        films = db_session.query(Film).all()
        assert len(films) == 1
        assert films[0].title == "The Matrix"
        assert films[0].year == 1999

        editions = (
            db_session.query(MovieEdition)
            .filter(MovieEdition.film_id == films[0].id)
            .order_by(MovieEdition.quality)
            .all()
        )
        assert len(editions) == 2
        assert editions[0].quality == "1080p"
        assert editions[1].quality == "2160p"

        media = db_session.query(MediaFile).all()
        assert len(media) == 2

    def test_bridge_same_title_different_year_two_films(
        self,
        db_session: Session,
        tmp_path: Path,
    ) -> None:
        """Same title but different year → two separate films."""
        from filmoteka.domain.catalog.models import Film
        from filmoteka.domain.importing.pipeline import run_import

        root = tmp_path
        v1 = root / "The.Matrix.1999.mkv"
        v2 = root / "The.Matrix.2021.mkv"
        _make_test_video(v1)
        _make_test_video(v2)
        config = _make_config(root)

        run_import(config, db_session)

        films = db_session.query(Film).order_by(Film.year).all()
        assert len(films) == 2
        assert films[0].year == 1999
        assert films[1].year == 2021


    # ── Dedup: re-import idempotency ──────────────────────────────

    def test_mediafile_dedup_on_reimport(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        """Re-importing the same file does not create duplicate MediaFile."""
        from filmoteka.domain.catalog.models import MediaFile
        from filmoteka.domain.importing.pipeline import run_import

        root = tmp_path
        video = root / "The.Matrix.1999.1080p.mkv"
        _make_test_video(video)
        config = _make_config(root)

        # First import
        r1 = run_import(config, db_session)
        assert r1.files_indexed == 1

        # Second import (same file)
        r2 = run_import(config, db_session)
        assert r2.files_indexed == 0  # skipped as duplicate

        # Only one MediaFile was created
        media_files = db_session.query(MediaFile).all()
        assert len(media_files) == 1

    def test_second_file_same_film_flags_needs_review(
        self, db_session: Session, tmp_path: Path
    ) -> None:
        """Importing a second file for the same film sets needs_review."""
        from filmoteka.domain.catalog.models import Film
        from filmoteka.domain.importing.pipeline import run_import

        root = tmp_path

        # Two files with same quality in different dirs — map to same edition → conflict
        v1 = root / "A" / "The.Matrix.1999.1080p.mkv"
        v2 = root / "B" / "The.Matrix.1999.1080p.mkv"
        v1.parent.mkdir(parents=True)
        v2.parent.mkdir(parents=True)
        _make_test_video(v1)
        _make_test_video(v2)
        config = _make_config(root)

        run_import(config, db_session)
        films = db_session.query(Film).all()
        assert len(films) == 1
        assert films[0].needs_review is True
