"""Admin-only endpoints."""

# ruff: noqa: B008  FastAPI requires Depends() in function signatures

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from filmoteka.api.auth import require_role
from filmoteka.api.dependencies import get_library_config
from filmoteka.domain.access.models import User
from filmoteka.domain.importing.pipeline import run_import
from filmoteka.infrastructure.database import get_db
from filmoteka.infrastructure.library_config import LibraryConfig

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/health")
def admin_health(
    current_user: User = Depends(require_role("admin")),
) -> dict[str, str]:
    """Simple admin-only health check."""
    return {"status": "ok", "role": current_user.role, "username": current_user.username}


@router.post("/import/scan")
def import_scan(
    current_user: User = Depends(require_role("admin")),
    config: LibraryConfig = Depends(get_library_config),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Run the full import pipeline: scan → probe → layout → bridge to catalog."""
    report = run_import(config, db)
    return report.to_dict()
