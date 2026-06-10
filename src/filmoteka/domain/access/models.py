"""User model for authentication and access control."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy import false as sa_false
from sqlalchemy import true as sa_true
from sqlalchemy.orm import Mapped, mapped_column

from filmoteka.infrastructure.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="user"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    incognito: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa_false(), nullable=False
    )
    age_group: Mapped[str | None] = mapped_column(String(8), nullable=True)
    exclude_family_from_recommendations: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa_true(), nullable=False
    )
    exclude_watched: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa_false(), nullable=False
    )
    include_external: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa_false(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


class UserFilmBlacklist(Base):
    """Many-to-many relationship: users blacklisting films."""

    __tablename__ = "user_film_blacklist"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    film_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("films.id", ondelete="CASCADE"), primary_key=True
    )

    def __repr__(self) -> str:
        return (
            f"<UserFilmBlacklist user_id={self.user_id} film_id={self.film_id}>"
        )
