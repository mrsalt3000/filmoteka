"""Admin-only endpoints."""

# ruff: noqa: B008  FastAPI requires Depends() in function signatures

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends

from filmoteka.api.auth import require_role
from filmoteka.api.dependencies import get_library_config
from filmoteka.domain.access.models import User
from filmoteka.domain.importing.pipeline import run_import
from filmoteka.infrastructure.database import SessionLocal
from filmoteka.infrastructure.library_config import LibraryConfig

router = APIRouter(prefix="/admin", tags=["admin"])

# In-memory store: { task_id: { "status": str, "report": dict|None, "error": str|None } }
_import_tasks: dict[str, dict[str, object]] = {}
_TASK_ID = "import-scan"  # single-slot for simplicity


@router.get("/health")
def admin_health(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, str]:
    """Simple admin-only health check."""
    return {"status": "ok", "role": current_user.role, "username": current_user.username}


@router.post("/import/scan", status_code=202)
def import_scan(
    current_user: User = Depends(require_role("admin")),
    config: LibraryConfig = Depends(get_library_config),
) -> dict[str, object]:
    """Start a background library scan.

    Returns immediately with 202. Poll ``GET /admin/import/status``
    for completion.
    """
    task = _import_tasks.get(_TASK_ID)
    if task and task["status"] == "running":
        return {"task_id": _TASK_ID, "status": "running", "message": "Scan already in progress"}

    _import_tasks[_TASK_ID] = {"status": "running", "report": None, "error": None}

    def _run() -> None:
        db = SessionLocal()
        try:
            report = run_import(config, db)
            _import_tasks[_TASK_ID] = {
                "status": "completed",
                "report": report.to_dict(),
                "error": None,
            }
        except Exception as exc:
            _import_tasks[_TASK_ID] = {
                "status": "failed",
                "report": None,
                "error": str(exc),
            }
        finally:
            db.close()

    threading.Thread(target=_run, daemon=True).start()

    return {"task_id": _TASK_ID, "status": "running", "message": "Scan started"}


@router.get("/import/status")
def import_status(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, object]:
    """Return the status of the last library scan."""
    task = _import_tasks.get(_TASK_ID)
    if task is None:
        return {"task_id": _TASK_ID, "status": "idle", "report": None, "error": None}
    return {"task_id": _TASK_ID, **task}
