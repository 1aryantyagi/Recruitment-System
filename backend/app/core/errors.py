"""Domain errors mapped to the standard error envelope (§4.2).

Every domain failure raises an `AppError` subclass; the global exception
handler renders it as `{"error": {"code", "message", "detail"}}`.
"""
from __future__ import annotations


class AppError(Exception):
    code: str = "ERROR"
    status_code: int = 400

    def __init__(self, message: str, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class DuplicateCandidateError(AppError):
    code = "DUPLICATE_CANDIDATE"
    status_code = 409


class ResumeLimitExceededError(AppError):
    code = "RESUME_LIMIT_EXCEEDED"
    status_code = 409


class DuplicateApplicationError(AppError):
    code = "DUPLICATE_APPLICATION"
    status_code = 409


class ActiveCallExistsError(AppError):
    code = "ACTIVE_CALL_EXISTS"
    status_code = 409


class AuthenticationError(AppError):
    """Missing/invalid credentials or token (401)."""

    code = "UNAUTHENTICATED"
    status_code = 401


class UnauthorizedError(AppError):
    """Valid identity but insufficient role (403)."""

    code = "UNAUTHORIZED"
    status_code = 403


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404


class BadRequestError(AppError):
    code = "BAD_REQUEST"
    status_code = 400
