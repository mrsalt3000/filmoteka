"""Structured JSON logging configuration."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Log formatter that outputs JSON records for structured logging.

    Fields: timestamp, level, logger, message, exception (if any).
    """

    def format(self, record: logging.LogRecord) -> str:
        now = datetime.fromtimestamp(record.created, tz=timezone.utc)
        log_entry: dict[str, object] = {
            "timestamp": now.isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)
        return json.dumps(log_entry, default=str, ensure_ascii=False)


def setup_json_logging(level: str = "INFO") -> None:
    """Configure the root logger and uvicorn loggers to use JSON format.

    Call once at application startup.
    """
    formatter = JsonFormatter()

    # Root handler
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    # Remove any existing handlers and add our JSON handler
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
    root_logger.addHandler(handler)

    # Ensure uvicorn loggers also use JSON
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers[:] = [handler]
        uvicorn_logger.propagate = False
