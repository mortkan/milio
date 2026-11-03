"""Core Microsoft Graph HTTP client.

Features:
- Token acquisition via MSAL (silent first, never interactive in background)
- Immutable IDs for Outlook Calendar (Prefer: IdType="ImmutableId")
- Centralized error handling and status checking
- Retry via graph/retry.py
- Pagination via graph/pagination.py
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx
import msal

from microsoft_integration.auth.msal_client import (
    acquire_token_silent,
    create_public_client,
)
from microsoft_integration.auth.token_cache import PersistedTokenCache
from microsoft_integration.config import MicrosoftSettings
from microsoft_integration.graph.errors import GraphAuthError, raise_for_status
from microsoft_integration.graph.pagination import collect_all, iter_pages
from microsoft_integration.graph.retry import with_retry

logger = logging.getLogger("microsoft.graph.client")


class GraphClient:
    """Async Microsoft Graph v1.0 HTTP client for a single authenticated account.

    Usage:
        async with GraphClient(settings, persisted_cache) as client:
            profile = await client.get("/me")
    """

    def __init__(
        self,
        settings: MicrosoftSettings,
        persisted_cache: PersistedTokenCache,
        use_immutable_ids: bool = True,
    ) -> None:
        self._settings = settings
        self._persisted_cache = persisted_cache
        self._use_immutable_ids = use_immutable_ids
        self._base_url = settings.microsoft_graph_base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "GraphClient":
        self._client = httpx.AsyncClient(timeout=30)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()
        self._persisted_cache.save_if_dirty()

    # ------------------------------------------------------------------
    # Token acquisition
    # ------------------------------------------------------------------

    def _get_access_token(self) -> str:
        """Acquire an access token silently. Raises GraphAuthError if not possible."""
        app = create_public_client(
            self._settings, token_cache=self._persisted_cache.msal_cache
        )
        result = acquire_token_silent(app, self._settings.microsoft_scopes)
        if result and "access_token" in result:
            self._persisted_cache.save_if_dirty()
            return result["access_token"]

        # Token acquisition failed — mark account for re-auth
        raise GraphAuthError(
            "Cannot acquire token silently. Account requires re-authentication.",
            status_code=401,
            error_code="token_refresh_failed",
        )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        token = self._get_access_token()
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._use_immutable_ids:
            headers["Prefer"] = 'IdType="ImmutableId"'
        if extra:
            headers.update(extra)
        return headers

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        assert self._client is not None, "GraphClient must be used as a context manager"

        async def _do() -> Dict[str, Any]:
            resp = await self._client.request(  # type: ignore[union-attr]
                method,
                url,
                headers=self._headers(extra_headers),
                json=json,
                params=params,
            )
            resp_json: Dict[str, Any] = {}
            try:
                if resp.content:
                    resp_json = resp.json()
            except Exception:
                pass

            raise_for_status(resp.status_code, resp_json, dict(resp.headers))
            return resp_json

        return await with_retry(_do, operation=f"{method} {url}")

    # ------------------------------------------------------------------
    # Public request methods
    # ------------------------------------------------------------------

    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        url = path if path.startswith("http") else f"{self._base_url}{path}"
        return await self._request("GET", url, params=params, extra_headers=extra_headers)

    async def post(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        url = path if path.startswith("http") else f"{self._base_url}{path}"
        return await self._request("POST", url, json=json, extra_headers=extra_headers)

    async def patch(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        url = path if path.startswith("http") else f"{self._base_url}{path}"
        return await self._request("PATCH", url, json=json, extra_headers=extra_headers)

    async def delete(self, path: str) -> None:
        url = path if path.startswith("http") else f"{self._base_url}{path}"
        assert self._client is not None

        async def _do() -> Dict[str, Any]:
            resp = await self._client.request("DELETE", url, headers=self._headers())  # type: ignore[union-attr]
            if resp.status_code not in (200, 204):
                resp_json: Dict[str, Any] = {}
                try:
                    resp_json = resp.json()
                except Exception:
                    pass
                raise_for_status(resp.status_code, resp_json, dict(resp.headers))
            return {}

        await with_retry(_do, operation=f"DELETE {url}")

    # ------------------------------------------------------------------
    # Pagination helpers
    # ------------------------------------------------------------------

    async def get_all(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        """Fetch all pages from a paginated Graph collection."""
        url = path if path.startswith("http") else f"{self._base_url}{path}"
        if params:
            # Build query string manually to pass params on first page only
            from urllib.parse import urlencode
            url = f"{url}?{urlencode(params)}"

        async def fetch(u: str) -> Dict[str, Any]:
            return await self.get(u)

        return await collect_all(fetch, url)

    async def iter_delta(
        self,
        path: str,
        delta_link: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ):
        """Async generator for delta queries. Yields (items, delta_link)."""
        if delta_link:
            url = delta_link  # Resume from previous state
        else:
            url = path if path.startswith("http") else f"{self._base_url}{path}"
            if params:
                from urllib.parse import urlencode
                url = f"{url}?{urlencode(params)}"

        all_items: List[Any] = []
        final_delta_link: Optional[str] = None
        next_link: Optional[str] = url

        while next_link:
            response = await self.get(next_link)
            items = response.get("value", [])
            all_items.extend(items)

            final_delta_link = response.get("@odata.deltaLink")
            next_link = response.get("@odata.nextLink")

        return all_items, final_delta_link
