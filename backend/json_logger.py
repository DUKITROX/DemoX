"""JSON-structured logging for DemoX agents.

Writes JSON-lines to files in the logs/ directory at project root,
alongside standard stderr output.
"""

import json
import logging
import os
from datetime import datetime, timezone


LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")


class JsonLineFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "event") and record.event is not None:
            log_entry["event"] = record.event
        if hasattr(record, "data") and record.data is not None:
            log_entry["data"] = record.data
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])
        return json.dumps(log_entry, default=str)


def setup_json_logger(name: str, filename: str) -> logging.Logger:
    """Create a logger that writes JSON-lines to logs/{filename} and also to stderr.

    Args:
        name: Logger name (e.g., "researcher", "presenter").
        filename: Log filename (e.g., "researcher.log", "presenter.log").

    Returns:
        Configured logger instance.
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, filename)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Prevent duplicate handlers if called multiple times
    if not any(
        isinstance(h, logging.FileHandler) and getattr(h, "_json_log", False)
        for h in logger.handlers
    ):
        # JSON file handler
        file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JsonLineFormatter())
        file_handler._json_log = True
        logger.addHandler(file_handler)

        # Human-readable stderr handler
        stderr_handler = logging.StreamHandler()
        stderr_handler.setLevel(logging.INFO)
        stderr_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
        )
        logger.addHandler(stderr_handler)

    return logger


def log_event(
    logger: logging.Logger,
    event: str,
    message: str,
    data: dict | None = None,
    level: int = logging.INFO,
):
    """Log a structured event with optional data payload.

    Args:
        logger: The logger instance.
        event: Event type (e.g., "crawl_start", "tool_call").
        message: Human-readable message.
        data: Optional dict of structured data to include.
        level: Log level (default INFO).
    """
    record = logger.makeRecord(
        name=logger.name,
        level=level,
        fn="",
        lno=0,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.event = event
    record.data = data
    logger.handle(record)
