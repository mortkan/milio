"""Pagination helper for Microsoft Graph API collections.

All Graph collection endpoints may return @odata.nextLink.
This module provides an async generator that transparently follows all pages.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator, Callable, Awaitable, Any

logger = logging.getLogger("microsoft.graph.pagination")


async def iter_pages(
    fetch_fn: Callable[[str], Awaitable[dict]],
    initial_url: str,
) -> AsyncIterator[list[Any]]:
    """Async generator that yields item lists from each page of a Graph collection.

    Args:
        fetch_fn: Async callable that takes a URL and returns the parsed JSON dict.
        initial_url: The first request URL (may include $filter, $select etc.).

    Yields:
        List of items from each page response.
    """
    url: str | None = initial_url
    page_num = 0

    while url:
        page_num += 1
        response = await fetch_fn(url)
        items = response.get("value", [])
        logger.debug("Pagination: page %d returned %d items", page_num, len(items))
        yield items

        url = response.get("@odata.nextLink")
        if url:
            logger.debug("Following nextLink (page %d+1)", page_num)


async def collect_all(
    fetch_fn: Callable[[str], Awaitable[dict]],
    initial_url: str,
) -> list[Any]:
    """Collect all items from a paginated Graph collection into a single list."""
    all_items = []
    async for page in iter_pages(fetch_fn, initial_url):
        all_items.extend(page)
    return all_items
