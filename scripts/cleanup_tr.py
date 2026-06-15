"""One-off cleanup: reset MediaFile paths from .tr back to originals.

Usage:
    docker compose exec -T api python < scripts/cleanup_tr.py          # dry-run
    docker compose exec -T api python < scripts/cleanup_tr.py --apply  # execute

This finds MediaFile records with file_path containing ".tr" before the
final extension (e.g. file.tr.mkv, file.tr.mp4).

For each record:
  If the ORIGINAL (no .tr) exists on disk:
    → delete the .tr file, restore file_path to original, reset audio_codec
  If only the .tr file exists (original was deleted):
    → rename .tr file back (file.tr.mkv → file.mkv), update path, reset audio_codec
"""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from filmoteka.domain.catalog.models import MediaFile  # noqa: E402
from filmoteka.infrastructure.database import SessionLocal  # noqa: E402


def _original_from_tr(path: Path) -> Path:
    """Derive the original path by stripping .tr from the stem.

    E.g.  Movie.tr.mkv  → Movie.mkv
          Movie.tr.mp4  → Movie.mkv  (originals were always .mkv)
    """
    suffixes = path.suffixes  # ['.tr', '.mkv'] or ['.tr', '.mp4']
    stem = path.stem  # "Movie.tr"
    if not stem.endswith(".tr"):
        return path  # no .tr in stem, shouldn't happen
    original_stem = stem[:-3]  # "Movie"
    # Originals were always .mkv
    return path.parent / f"{original_stem}.mkv"


def _tr_stripped_name(path: Path) -> tuple[Path, str]:
    """Return (new_path, new_basename) with .tr removed from the filename.

    E.g.  /dir/Movie.tr.mkv  →  (/dir/Movie.mkv, 'Movie.mkv')
    """
    suffixes = path.suffixes  # ['.tr', '.mkv']
    stem = path.stem  # "Movie.tr"
    restem = stem[:-3] if stem.endswith(".tr") else stem
    # Use the last suffix (original container format)
    new_name = f"{restem}{suffixes[-1]}"
    return path.parent / new_name, new_name


def main() -> None:
    apply = "--apply" in sys.argv
    db = SessionLocal()
    try:
        tr_records = (
            db.query(MediaFile)
            .filter(MediaFile.file_path.ilike("%.tr.%"))
            .all()
        )
        if not tr_records:
            print("No MediaFile records with .tr in path found.")
            return

        print(f"Found {len(tr_records)} MediaFile record(s) with .tr in path:\n")

        restored = 0         # original existed → restored
        renamed = 0          # original not found → renamed file back
        skipped_orphan = 0   # neither original nor .tr file on disk

        for mf in sorted(tr_records, key=lambda r: r.id):
            tr_path = Path(mf.file_path)
            orig = _original_from_tr(tr_path)

            if orig.is_file():
                # CASE 1: original exists → delete .tr, restore original
                print(f"  {mf.id:>4d}  {mf.file_path}")
                print(f"          → ORIGINAL EXISTS: restore to {orig.name}")
                if apply:
                    tr_path.unlink(missing_ok=True)
                    mf.file_path = str(orig)
                    mf.audio_codec = None
                    db.commit()
                restored += 1

            elif tr_path.is_file():
                # CASE 2: only .tr file on disk → rename without .tr
                new_path, new_name = _tr_stripped_name(tr_path)
                print(f"  {mf.id:>4d}  {mf.file_path}")
                print(f"          → ONLY .tr EXISTS: rename to {new_name}")
                if apply:
                    if new_path.is_file():
                        print(f"          ⚠ {new_name} already exists — skipping rename")
                        skipped_orphan += 1
                    else:
                        tr_path.rename(new_path)
                        mf.file_path = str(new_path)
                        mf.audio_codec = None
                        db.commit()
                renamed += 1

            else:
                # CASE 3: neither file on disk
                print(f"  {mf.id:>4d}  {mf.file_path}")
                print(f"          → NEITHER FILE ON DISK — leaving DB as-is")
                skipped_orphan += 1

        print(f"\n---")
        print(f"Restored (original existed):  {restored}")
        print(f"Renamed (.tr → plain name):   {renamed}")
        print(f"Skipped (no file on disk):    {skipped_orphan}")
        if apply:
            print("Status: ✅ APPLIED")
        else:
            print("Status: 🔍 DRY-RUN — re-run with --apply to execute")

    finally:
        db.close()


if __name__ == "__main__":
    main()
