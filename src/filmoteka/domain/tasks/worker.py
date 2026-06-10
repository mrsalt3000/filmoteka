"""Background job runner — lightweight threading-based job queue."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime

from filmoteka.domain.tasks.models import (
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_PENDING,
    JOB_RUNNING,
    BackgroundJob,
)
from filmoteka.infrastructure.database import SessionLocal


def run_background_job(
    job_type: str,
    fn: Callable[..., dict | None],
    *args: object,
    session_factory: type = SessionLocal,
    **kwargs: object,
) -> BackgroundJob:
    """Create a ``BackgroundJob`` record and run *fn* in a daemon thread.

    The job status is updated as the function progresses:
    ``pending`` → ``running`` → ``completed`` / ``failed``.

    *session_factory* is used to create DB sessions (default ``SessionLocal``).

    Returns the job record (already flushed to DB).
    """
    db = session_factory()
    try:
        job = BackgroundJob(type=job_type, status=JOB_PENDING)
        db.add(job)
        db.commit()
        db.refresh(job)
        job_id = job.id
    finally:
        db.close()

    def _run() -> None:
        job_db = session_factory()
        try:
            # Mark as running
            j = job_db.get(BackgroundJob, job_id)
            if j is not None:
                j.status = JOB_RUNNING
                j.started_at = datetime.now()
                job_db.commit()

            # Execute the function
            result = fn(*args, **kwargs)

            # Mark as completed
            j = job_db.get(BackgroundJob, job_id)
            if j is not None:
                j.status = JOB_COMPLETED
                j.completed_at = datetime.now()
                j.result = result
                job_db.commit()
        except Exception as exc:
            job_db.rollback()
            j = job_db.get(BackgroundJob, job_id)
            if j is not None:
                j.status = JOB_FAILED
                j.completed_at = datetime.now()
                j.error = str(exc)
                job_db.commit()
        finally:
            job_db.close()

    threading.Thread(target=_run, daemon=True).start()
    return job
