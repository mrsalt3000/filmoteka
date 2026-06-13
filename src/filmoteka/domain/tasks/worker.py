"""Background job runner — lightweight threading-based job queue."""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime

from filmoteka.domain.tasks.models import (
    JOB_CANCELLED,
    JOB_COMPLETED,
    JOB_FAILED,
    JOB_PENDING,
    JOB_RUNNING,
    BackgroundJob,
)
from filmoteka.infrastructure.database import SessionLocal


def should_stop(
    job_id: int,
    session_factory: type = SessionLocal,
) -> bool:
    """Check whether a background job has been requested to stop.

    Opens a fresh DB session, fetches the job, and returns ``True``
    if ``cancel_requested`` is set or the status is ``cancelled``.
    Worker functions with a processing loop should call this after
    each iteration to support early termination.
    """
    db = session_factory()
    try:
        job = db.get(BackgroundJob, job_id)
        return job is not None and (
            job.cancel_requested or job.status == JOB_CANCELLED
        )
    finally:
        db.close()


def run_background_job(
    job_type: str,
    fn: Callable[..., dict | None],
    *args: object,
    session_factory: type = SessionLocal,
    **kwargs: object,
) -> BackgroundJob:
    """Create a ``BackgroundJob`` record and run *fn* in a daemon thread.

    The job status is updated as the function progresses:
    ``pending`` → ``running`` → ``completed`` / ``failed`` / ``cancelled``.

    If the job is cancelled (via ``cancel_requested``) while *fn* runs,
    *fn* is responsible for checking ``should_stop()`` and returning
    early.  After *fn* returns, ``_run`` checks ``cancel_requested``
    and honours the ``cancelled`` status instead of overwriting it.

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

            # Check if cancelled was requested while fn was running
            j = job_db.get(BackgroundJob, job_id)
            if j is not None:
                if j.cancel_requested or j.status == JOB_CANCELLED:
                    # Honour cancelled — keep the status, just attach result
                    j.result = result
                    job_db.commit()
                else:
                    j.status = JOB_COMPLETED
                    j.completed_at = datetime.now()
                    j.result = result
                    job_db.commit()
        except Exception as exc:
            job_db.rollback()
            j = job_db.get(BackgroundJob, job_id)
            if j is not None and not j.cancel_requested:
                j.status = JOB_FAILED
                j.completed_at = datetime.now()
                j.error = str(exc)
                job_db.commit()
        finally:
            job_db.close()

    threading.Thread(target=_run, daemon=True).start()
    return job
