from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
    )

    database_url: str
    redis_url: str
    secret_key: str

    library_spec_path: Path = Path("specs/library.yaml")

    # Override roots from .env — these take precedence over library.yaml values.
    downloads_root: Path | None = None
    library_root: Path | None = None

    # External metadata providers
    omdb_api_key: str | None = None

    # LLM for mood-based suggestions (e.g. http://localhost:11434 for Ollama)
    llm_api_url: str | None = None

    # Backup
    backup_dir: str = "/backups"

    version: str = "0.1.0"


settings = Settings()  # type: ignore[call-arg]
