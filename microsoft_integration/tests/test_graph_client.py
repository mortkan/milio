"""Tests for Microsoft Graph error handling and retry logic."""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from microsoft_integration.graph.errors import (
    GraphAuthError,
    GraphDeltaExpiredError,
    GraphError,
    GraphNotFoundError,
    GraphServerError,
    GraphThrottleError,
    raise_for_status,
)
from microsoft_integration.graph.retry import with_retry


class TestRaiseForStatus:
    def test_200_no_error(self):
        raise_for_status(200, {}, {})  # Should not raise

    def test_429_raises_throttle(self):
        with pytest.raises(GraphThrottleError) as exc_info:
            raise_for_status(429, {}, {"Retry-After": "30"})
        assert exc_info.value.retry_after == 30

    def test_401_raises_auth(self):
        with pytest.raises(GraphAuthError):
            raise_for_status(401, {"error": {"code": "InvalidAuthenticationToken", "message": "Unauthorized"}}, {})

    def test_404_raises_not_found(self):
        with pytest.raises(GraphNotFoundError):
            raise_for_status(404, {"error": {"code": "NotFound", "message": "Not found"}}, {})

    def test_500_raises_server(self):
        with pytest.raises(GraphServerError):
            raise_for_status(500, {"error": {"code": "InternalServerError", "message": "Oops"}}, {})

    def test_410_delta_expired(self):
        with pytest.raises(GraphDeltaExpiredError):
            raise_for_status(410, {"error": {"code": "syncStateNotFound", "message": "Delta expired"}}, {})


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_retry_on_throttle(self):
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise GraphThrottleError(retry_after=0)
            return "success"

        with patch("microsoft_integration.graph.retry.asyncio.sleep", new=AsyncMock()):
            result = await with_retry(flaky, "test")
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_auth_error(self):
        async def always_auth_error():
            raise GraphAuthError("Unauthorized", status_code=401)

        with pytest.raises(GraphAuthError):
            await with_retry(always_auth_error)

    @pytest.mark.asyncio
    async def test_success_first_try(self):
        async def success():
            return 42

        result = await with_retry(success)
        assert result == 42
