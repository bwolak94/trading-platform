"""Structured JSON logging configuration for the AI Trading Navigator.

Usage:
    from app.core.logging import get_logger

    logger = get_logger(__name__)
    logger.info("Signal generated", extra={"asset": "BTC/USDT", "confidence": 72.5})

Log output (single-line JSON):
    {"timestamp": "2025-01-15T12:30:00.123Z", "level": "INFO",
     "logger": "app.tasks", "message": "Signal generated",
     "asset": "BTC/USDT", "confidence": 72.5}
"""

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# Per-request correlation ID — set by the correlation middleware in main.py
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class CorrelationIdFilter(logging.Filter):
    """Injects the current request_id ContextVar into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get("-")  # type: ignore[attr-defined]
        return True


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects.

    Includes timestamp (ISO-8601 UTC), level, logger name, message,
    and any extra fields passed via the ``extra`` dict.
    """

    # Fields that belong to the standard LogRecord and should not leak
    # into the JSON ``extra`` section.
    _RESERVED_ATTRS: frozenset[str] = frozenset({
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "message", "module",
        "msecs", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "request_id", "stack_info", "taskName", "thread", "threadName",
    })

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a LogRecord into a JSON string.

        Args:
            record: The log record to format.

        Returns:
            A single-line JSON string.
        """
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }

        # Attach any extra fields the caller provided
        for key, value in record.__dict__.items():
            if key not in self._RESERVED_ATTRS and key not in log_entry:
                try:
                    json.dumps(value)  # ensure serialisable
                    log_entry[key] = value
                except (TypeError, ValueError):
                    log_entry[key] = str(value)

        # Attach exception info if present
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        if record.stack_info:
            log_entry["stack_info"] = record.stack_info

        return json.dumps(log_entry, default=str)


def _configure_root_logger() -> None:
    """Configure the root logger with JSON formatting.

    Called once on first ``get_logger`` invocation. Reads LOG_LEVEL from
    the environment (default: INFO).
    """
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    root = logging.getLogger()

    # Avoid adding duplicate handlers on repeated calls
    if any(isinstance(h, logging.StreamHandler) and isinstance(h.formatter, JSONFormatter) for h in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    handler.setLevel(log_level)
    handler.addFilter(CorrelationIdFilter())

    root.setLevel(log_level)
    root.addHandler(handler)


_configured = False


def set_request_id(request_id: str) -> None:
    """Set the correlation ID for the current async context (called by middleware)."""
    _request_id_var.set(request_id)


def get_logger(name: str) -> logging.Logger:
    """Return a structured JSON logger for the given module name.

    On the first call this also configures the root logger so that all
    loggers in the application emit JSON.

    Args:
        name: Logger name, typically ``__name__``.

    Returns:
        A ``logging.Logger`` instance.
    """
    global _configured  # noqa: PLW0603
    if not _configured:
        _configure_root_logger()
        _configured = True

    return logging.getLogger(name)
