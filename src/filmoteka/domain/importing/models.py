"""Models for import pipeline: import runs and candidates."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from filmoteka.infrastructure.database import Base


class ImportRun(Base):
    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(default=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running"
    )
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    candidates: Mapped[list[ImportCandidate]] = relationship(
        back_populates="import_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<ImportRun id={self.id} status={self.status!r}"
            f" files={self.file_count}>"
        )


# Import candidate statuses
CANDIDATE_PENDING = "pending"
CANDIDATE_PROBED = "probed"
CANDIDATE_IMPORTED = "imported"
CANDIDATE_ERROR = "error"


class ImportCandidate(Base):
    __tablename__ = "import_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("import_runs.id", ondelete="CASCADE"), nullable=False
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CANDIDATE_PENDING
    )

    # Probe results — populated by ffprobe after scan
    probed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_secs: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    codec: Mapped[str | None] = mapped_column(String(32), nullable=True)
    audio_codec: Mapped[str | None] = mapped_column(String(32), nullable=True)
    audio_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subtitle_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    import_run: Mapped[ImportRun] = relationship(back_populates="candidates")

    def __repr__(self) -> str:
        return (
            f"<ImportCandidate id={self.id} run={self.import_run_id}"
            f" status={self.status!r} path={self.file_path!r}>"
        )
