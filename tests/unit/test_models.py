"""Unit tests for core catalog domain models."""

from __future__ import annotations


class TestFilm:
    """Film model construction and representation."""

    def test_create_film_minimal(self) -> None:
        from filmoteka.domain.catalog.models import Film

        f = Film(title="Test Movie")
        assert f.title == "Test Movie"
        assert f.year is None
        assert f.description is None
        assert f.id is None  # not persisted

    def test_create_film_full(self) -> None:
        from filmoteka.domain.catalog.models import Film

        f = Film(title="Inception", year=2010, description="A mind-bending thriller")
        assert f.title == "Inception"
        assert f.year == 2010
        assert f.description == "A mind-bending thriller"

    def test_film_repr(self) -> None:
        from filmoteka.domain.catalog.models import Film

        f = Film(title="Alien")
        assert repr(f) == "<Film id=None title='Alien'>"


class TestPerson:
    """Person model construction and representation."""

    def test_create_person(self) -> None:
        from filmoteka.domain.catalog.models import Person

        p = Person(name="Ridley Scott")
        assert p.name == "Ridley Scott"

    def test_person_repr(self) -> None:
        from filmoteka.domain.catalog.models import Person

        p = Person(name="Ridley Scott")
        assert repr(p) == "<Person id=None name='Ridley Scott'>"


class TestGenre:
    """Genre model construction and representation."""

    def test_create_genre(self) -> None:
        from filmoteka.domain.catalog.models import Genre

        g = Genre(name="Science Fiction", slug="sci-fi")
        assert g.name == "Science Fiction"
        assert g.slug == "sci-fi"

    def test_genre_repr(self) -> None:
        from filmoteka.domain.catalog.models import Genre

        g = Genre(name="Comedy", slug="comedy")
        assert repr(g) == "<Genre id=None name='Comedy'>"


class TestMovieEdition:
    """MovieEdition model construction and representation."""

    def test_create_edition(self) -> None:
        from filmoteka.domain.catalog.models import MovieEdition

        ed = MovieEdition(film_id=1, edition_name="Director's Cut", quality="1080p")
        assert ed.film_id == 1
        assert ed.edition_name == "Director's Cut"
        assert ed.quality == "1080p"

    def test_edition_repr(self) -> None:
        from filmoteka.domain.catalog.models import MovieEdition

        ed = MovieEdition(film_id=5, edition_name="Extended")
        assert repr(ed) == "<MovieEdition id=None film_id=5 edition='Extended'>"


class TestMediaFile:
    """MediaFile model construction and representation."""

    def test_create_media_file(self) -> None:
        from filmoteka.domain.catalog.models import MediaFile

        mf = MediaFile(edition_id=1, file_path="/media/movies/test.mp4")
        assert mf.edition_id == 1
        assert mf.file_path == "/media/movies/test.mp4"
        assert mf.file_size is None

    def test_media_file_with_tech_attrs(self) -> None:
        from filmoteka.domain.catalog.models import MediaFile

        mf = MediaFile(
            edition_id=1,
            file_path="/media/movies/test.mp4",
            file_size=1_500_000_000,
            duration_secs=7200.0,
            width=1920,
            height=1080,
            codec="h264",
        )
        assert mf.file_size == 1_500_000_000
        assert mf.duration_secs == 7200.0
        assert mf.codec == "h264"

    def test_media_file_repr(self) -> None:
        from filmoteka.domain.catalog.models import MediaFile

        mf = MediaFile(edition_id=1, file_path="/media/movies/test.mp4")
        assert repr(mf) == "<MediaFile id=None path='/media/movies/test.mp4'>"


class TestRelationships:
    """Verify relationships are configured (in-memory, no DB)."""

    def test_film_has_editions_list(self) -> None:
        from filmoteka.domain.catalog.models import Film

        f = Film(title="Test")
        assert f.editions == []

    def test_film_has_genres_list(self) -> None:
        from filmoteka.domain.catalog.models import Film

        f = Film(title="Test")
        assert f.genres == []

    def test_film_has_persons_list(self) -> None:
        from filmoteka.domain.catalog.models import Film

        f = Film(title="Test")
        assert f.persons == []

    def test_genre_has_films_list(self) -> None:
        from filmoteka.domain.catalog.models import Genre

        g = Genre(name="Sci-Fi", slug="sci-fi")
        assert g.films == []

    def test_edition_has_media_files_list(self) -> None:
        from filmoteka.domain.catalog.models import MovieEdition

        ed = MovieEdition(film_id=1)
        assert ed.media_files == []
