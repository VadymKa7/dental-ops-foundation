import json
import logging

from app.core.logging import JsonFormatter, stack_frames


def test_formatter_keeps_approved_fields_and_drops_exception_text() -> None:
    formatter = JsonFormatter()
    try:
        raise RuntimeError("postgresql+asyncpg://dental:secret@localhost/dental")
    except RuntimeError as exc:
        record = logging.LogRecord(
            name="app.test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="database readiness check failed",
            args=(),
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        record.error_type = "RuntimeError"
        record.error_frames = stack_frames(exc)
        record.email = "ada@example.com"
        rendered = formatter.format(record)

    payload = json.loads(rendered)
    assert payload["message"] == "database readiness check failed"
    assert payload["error_type"] == "RuntimeError"
    assert payload["error_frames"]
    assert "secret" not in rendered
    assert "postgresql+asyncpg" not in rendered
    assert "ada@example.com" not in rendered
    assert "email" not in payload


def test_stack_frames_omit_the_exception_message() -> None:
    try:
        raise ValueError("ada@example.com")
    except ValueError as exc:
        frames = stack_frames(exc)

    assert frames
    assert all("ada@example.com" not in frame for frame in frames)
    assert all(frame.count(":") == 1 for frame in frames)
