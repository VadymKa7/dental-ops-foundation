"""Domain errors raised by services.

HTTP status mapping lives in the API layer. Services do not import FastAPI.
"""


class AppError(Exception):
    """Expected application failure with a stable client-facing code."""

    def __init__(self, message: str, *, code: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class NotFoundError(AppError):
    def __init__(self, message: str, *, code: str = "not_found") -> None:
        super().__init__(message, code=code, status_code=404)


class ConflictError(AppError):
    def __init__(self, message: str, *, code: str = "conflict") -> None:
        super().__init__(message, code=code, status_code=409)


class DomainValidationError(AppError):
    def __init__(self, message: str, *, code: str = "domain_validation_error") -> None:
        super().__init__(message, code=code, status_code=422)
