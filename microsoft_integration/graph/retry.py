"""Retry policy for Microsoft Graph API requests.

Handles:
- 429 Too Many Requests (respects Retry-After header)
- 408 Request Timeout
- 5xx Server Errors
- Exponential backoff with jitter

Does NOT retry:
- 400 Bad Request
- 401 Unauthorized (persistent — triggers re-auth)
- 403 Forbidden
- 404 Not Found (unless explicitly requested)
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TypeVar, Callable, Awaitable

from microsoft_integration.graph.errors import (
    GraphAuthError,
    GraphError,
    GraphNotFoundError,
    GraphServerError,
    GraphThrottleError,
)

logger = logging.getLogger("microsoft.graph.retry")

T = TypeVar("T")

# Status codes eligible for retry
_RETRYABLE_CODES = {408, 429, 500, 502, 503, 504}
_MAX_RETRIES = 5
_BASE_BACKOFF = 1.0  # seconds
_MAX_BACKOFF = 60.0  # seconds


async def with_retry(coro_fn: Callable[[], Awaitable[T]], operation: str = "") -> T:
    """Execute an async callable with retry logic for transient Graph errors."""
    last_exc: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            return await coro_fn()
        except GraphThrottleError as exc:
            wait = exc.retry_after or _backoff(attempt)
            logger.warning(
                "Graph throttled%s — waiting %ds (attempt %d/%d)",
                f" [{operation}]" if operation else "",
                wait,
                attempt + 1,
                _MAX_RETRIES,
            )
            last_exc = exc
            await asyncio.sleep(wait)
        except GraphServerError as exc:
            wait = _backoff(attempt)
            logger.warning(
                "Graph server error %s%s — backoff %ds (attempt %d/%d)",
                exc.status_code,
                f" [{operation}]" if operation else "",
                wait,
                attempt + 1,
                _MAX_RETRIES,
            )
            last_exc = exc
            await asyncio.sleep(wait)
        except (GraphAuthError, GraphNotFoundError, GraphError):
            raise  # Non-retryable

    raise last_exc  # type: ignore[misc]


def _backoff(attempt: int) -> float:
    """Exponential backoff with full jitter."""
    cap = min(_MAX_BACKOFF, _BASE_BACKOFF * (2 ** attempt))
    return random.uniform(0, cap)
