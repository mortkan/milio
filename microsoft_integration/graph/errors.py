"""Microsoft Graph API error types and handling."""
from __future__ import annotations

from typing import Optional


class GraphError(Exception):
    """Base exception for Microsoft Graph API errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        retry_after: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.retry_after = retry_after

    def __repr__(self) -> str:
        return (
            f"GraphError(status={self.status_code}, code={self.error_code!r}, "
            f"message={str(self)!r})"
        )


class GraphThrottleError(GraphError):
    """HTTP 429 Too Many Requests from Microsoft Graph."""

    def __init__(self, retry_after: int = 60) -> None:
        super().__init__(
            f"Microsoft Graph throttled request (retry after {retry_after}s)",
            status_code=429,
            error_code="activityLimitReached",
            retry_after=retry_after,
        )


class GraphAuthError(GraphError):
    """Authentication or authorization failure (401/403)."""
    pass


class GraphNotFoundError(GraphError):
    """Resource not found (404)."""
    pass


class GraphServerError(GraphError):
    """Server-side transient error (5xx)."""
    pass


class GraphDeltaExpiredError(GraphError):
    """Delta token has expired — a full sync is required."""
    pass


def raise_for_status(status_code: int, response_json: dict, headers: dict) -> None:
    """Raise the appropriate GraphError based on status code and response body."""
    if status_code < 400:
        return

    error_body = response_json.get("error", {})
    code = error_body.get("code", "")
    message = error_body.get("message", f"HTTP {status_code}")

    if status_code == 429:
        retry_after = int(headers.get("Retry-After", "60"))
        raise GraphThrottleError(retry_after=retry_after)

    if status_code in (401, 403):
        raise GraphAuthError(message, status_code=status_code, error_code=code)

    if status_code == 404:
        raise GraphNotFoundError(message, status_code=status_code, error_code=code)

    if status_code == 410 or code == "syncStateNotFound":
        raise GraphDeltaExpiredError(
            "Delta token expired or not found", status_code=status_code, error_code=code
        )

    if status_code >= 500:
        raise GraphServerError(message, status_code=status_code, error_code=code)

    raise GraphError(message, status_code=status_code, error_code=code)
