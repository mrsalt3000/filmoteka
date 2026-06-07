"""Core catalog domain models.

SQLAlchemy declarative models following ADR-010 separation:
- Film (movie — the abstract work)
- MovieEdition (a concrete release / translation / cut)
- MediaFile (a physical media file on disk)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from filmoteka.infrastructure.database import Base

# ---------------------------------------------------------------------------
# Association tables
# ---------------------------------------------------------------------------

film_genre = Table(
    "film_genre",
    Base.metadata,
    Column(
        "film_id",
        ForeignKey("films.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "genre_id",
        ForeignKey("genres.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

film_person = Table(
    "film_person",
    Base.metadata,
    Column(
        "film_id",
        ForeignKey("films.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "person_id",
        ForeignKey("persons.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("role", String(50), nullable=False),
)


# ---------------------------------------------------------------------------
# Core entities
# ---------------------------------------------------------------------------

class Film(Base):
    __tablename__ = "films"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    poster_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    poster_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kinopoisk_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        default=datetime.now, onupdate=datetime.now
    )

    editions: Mapped[list[MovieEdition]] = relationship(back_populates="film")
    genres: Mapped[list[Genre]] = relationship(secondary=film_genre, back_populates="films")
    persons: Mapped[list[Person]] = relationship(secondary=film_person, back_populates="films")

    def __repr__(self) -> str:
        return f"<Film id={self.id} title={self.title!r}>"


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    films: Mapped[list[Film]] = relationship(secondary=film_person, back_populates="persons")

    def __repr__(self) -> str:
        return f"<Person id={self.id} name={self.name!r}>"


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    films: Mapped[list[Film]] = relationship(secondary=film_genre, back_populates="genres")

    def __repr__(self) -> str:
        return f"<Genre id={self.id} name={self.name!r}>"


class MovieEdition(Base):
    __tablename__ = "movie_editions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    film_id: Mapped[int] = mapped_column(
        ForeignKey("films.id", ondelete="CASCADE"), nullable=False, index=True
    )
    edition_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    film: Mapped[Film] = relationship(back_populates="editions")
    media_files: Mapped[list[MediaFile]] = relationship(back_populates="edition")

    __table_args__ = (
        UniqueConstraint("film_id", "edition_name", "quality", "language"),
    )

    def __repr__(self) -> str:
        return (
            f"<MovieEdition id={self.id} film_id={self.film_id}"
            f" edition={self.edition_name!r}>"
        )


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    edition_id: Mapped[int] = mapped_column(
        ForeignKey("movie_editions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(
        String(1024), nullable=False, unique=True
    )
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    duration_secs: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    codec: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audio_codec: Mapped[str | None] = mapped_column(String(64), nullable=True)
    subtitle_languages: Mapped[str | None] = mapped_column(
        String(256), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    edition: Mapped[MovieEdition] = relationship(back_populates="media_files")

    def __repr__(self) -> str:
        return f"<MediaFile id={self.id} path={self.file_path!r}>"
