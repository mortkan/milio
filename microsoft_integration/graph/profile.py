"""Microsoft Graph: User profile."""
from __future__ import annotations

import logging
from typing import Optional

from microsoft_integration.graph.client import GraphClient

logger = logging.getLogger("microsoft.graph.profile")


async def get_my_profile(client: GraphClient) -> dict:
    """Fetch the signed-in user's basic profile from /me."""
    return await client.get(
        "/me",
        params={"$select": "id,displayName,mail,userPrincipalName,accountEnabled"},
    )


async def get_profile_photo_url(client: GraphClient) -> Optional[str]:
    """Return the URL for the user's profile photo, or None if unavailable."""
    try:
        meta = await client.get("/me/photo")
        return "/me/photo/$value"
    except Exception:
        return None
