"""Models for the watching domain: watch events and playback state."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Integer
from sqlalchemy import false as sa_false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from filmoteka.infrastructure.database import Base

if TYPE_CHECKING:
    from filmoteka.domain.access.models import User
    from filmoteka.domain.catalog.models import MediaFile


class WatchEvent(Base):
    __tablename__ = "watch_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_file_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("media_files.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(default=datetime.now)
    last_position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    finished: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    incognito: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sa_false()
    )

    media_file: Mapped[MediaFile] = relationship()
    user: Mapped[User] = relationship()

    def __repr__(self) -> str:
        return (
            f"<WatchEvent id={self.id} media={self.media_file_id}"
            f" user={self.user_id} pos={self.last_position}>"
        )
