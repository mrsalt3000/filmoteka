from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class PathsConfig(BaseModel):
    downloads_root: Path = Path("/media/downloads")
    target_root: Path = Path("/media/library")


class ImportConfig(BaseModel):
    extensions: list[str] = Field(
        default=[".mp4", ".mkv", ".avi", ".mov", ".m4v", ".ts"]
    )
    max_file_size_gb: int = 50


class LibraryConfig(BaseModel):
    paths: PathsConfig
    import_: ImportConfig = Field(alias="import")
    organization: str = "by_year"


def load_library_config(path: Path) -> LibraryConfig:
    if not path.exists():
        raise FileNotFoundError(f"Library config not found: {path}")

    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid library config: expected a mapping, got {type(data).__name__}")

    return LibraryConfig.model_validate(data)
