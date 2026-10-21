"""JSON logs for the API process.

Only a fixed set of extra fields is written. Exception messages are omitted
because database drivers put DSNs and statement parameters in those messages.
"""

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TextIO

_ALLOWED_EXTRA = frozenset(
    {
        "error_type",
        "error_frames",
        "http_method",
        "path",
        "status_code",
        "duration_ms",
    }
)

_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class JsonFormatter(logging.Formatter):
    """Serialize a log record without exception text or unapproved fields."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _ALLOWED_EXTRA:
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, default=str)


class JsonLogHandler(logging.StreamHandler[TextIO]):
    def __init__(self) -> None:
        super().__init__()
        self.setFormatter(JsonFormatter())


def _keep_handler(handler: logging.Handler) -> bool:
    # Drop the plain stderr handler Uvicorn installs. Keep subclasses such as
    # JsonLogHandler and pytest's capture handler.
    return type(handler) is not logging.StreamHandler


def configure_logging(level: str) -> None:
    """Attach one JSON handler to the root logger.

    Plain StreamHandler instances are removed so Uvicorn does not also write a
    second unstructured line. Subclasses stay attached, which keeps pytest's
    log capture working. Uvicorn's access logger is disabled because
    AccessLogMiddleware already records the request.
    """
    numeric_level = _LEVELS.get(level, logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers = [handler for handler in root.handlers if _keep_handler(handler)]
    if not any(isinstance(handler, JsonLogHandler) for handler in root.handlers):
        root.addHandler(JsonLogHandler())

    for logger_name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers = [handler for handler in logger.handlers if _keep_handler(handler)]
        logger.propagate = True
        logger.setLevel(numeric_level)

    # The app middleware writes the access line. Uvicorn's access logger would duplicate it.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers = []
    access_logger.propagate = False
    access_logger.disabled = True


def stack_frames(exc: BaseException, *, limit: int = 20) -> list[str]:
    """Return file:line frames for an exception, without the exception message."""
    frames: list[str] = []
    cursor = exc.__traceback__
    while cursor is not None and len(frames) < limit:
        code = cursor.tb_frame.f_code
        frames.append(f"{code.co_filename}:{cursor.tb_lineno}")
        cursor = cursor.tb_next
    return frames


def log_failure(logger: logging.Logger, message: str, exc: BaseException) -> None:
    """Log a failure by type and stack location."""
    extra: Mapping[str, object] = {
        "error_type": exc.__class__.__name__,
        "error_frames": stack_frames(exc),
    }
    logger.error(message, extra=dict(extra))
