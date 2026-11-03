"""MSAL PublicClientApplication factory.

Creates and configures MSAL clients for Device Code Flow and
(future) Authorization Code Flow + PKCE.
"""
from __future__ import annotations

import logging
from typing import List, Optional

import msal

from microsoft_integration.config import MicrosoftSettings

logger = logging.getLogger("microsoft.auth.msal_client")


def create_public_client(
    settings: MicrosoftSettings,
    token_cache: Optional[msal.SerializableTokenCache] = None,
) -> msal.PublicClientApplication:
    """Create a MSAL PublicClientApplication for delegated flows.

    Args:
        settings: Current Microsoft integration settings.
        token_cache: Optional pre-loaded MSAL SerializableTokenCache.

    Returns:
        Configured PublicClientApplication.
    """
    if not settings.client_configured:
        raise RuntimeError(
            "MICROSOFT_CLIENT_ID is not configured. "
            "Set it in .env.microsoft before starting the integration service."
        )

    app = msal.PublicClientApplication(
        client_id=settings.microsoft_client_id,
        authority=settings.authority,
        token_cache=token_cache,
    )
    logger.debug(
        "MSAL PublicClientApplication created for client_id=%s authority=%s",
        settings.microsoft_client_id,
        settings.authority,
    )
    return app


def acquire_token_silent(
    app: msal.PublicClientApplication,
    scopes: List[str],
    account: Optional[msal.Account] = None,
) -> Optional[dict]:
    """Try to get a token from the cache without user interaction.

    Returns the token response dict if successful, None otherwise.
    """
    accounts = app.get_accounts()
    if not accounts:
        return None

    target_account = account or accounts[0]
    result = app.acquire_token_silent(scopes=scopes, account=target_account)
    if result and "access_token" in result:
        return result
    return None


def get_first_account(app: msal.PublicClientApplication) -> Optional[msal.Account]:
    """Return the first cached account if any."""
    accounts = app.get_accounts()
    return accounts[0] if accounts else None
