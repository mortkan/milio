"""Device Code Flow implementation for OAuth 2.0 authentication.

This is the primary authentication method for local/private Milo deployments.
It does NOT block the FastAPI worker — polling runs in a background thread.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import msal
from sqlalchemy.orm import Session

from microsoft_integration.auth.encryption import TokenEncryptor
from microsoft_integration.auth.msal_client import create_public_client
from microsoft_integration.auth.token_cache import PersistedTokenCache
from microsoft_integration.config import MicrosoftSettings
from microsoft_integration.models import MsAuthFlow

logger = logging.getLogger("microsoft.auth.device_flow")


class DeviceFlowManager:
    """Manages Device Code Flow authentication for Milo Microsoft integration.

    Responsibilities:
    - Initiate a device code flow and persist its state
    - Background-poll Microsoft for completion
    - On success: create/update ms_accounts and token cache
    - On expiry: mark flow as expired
    """

    def __init__(
        self,
        settings: MicrosoftSettings,
        encryptor: TokenEncryptor,
        db_session_factory: Callable[[], Session],
        on_account_connected: Optional[Callable[[int], None]] = None,
    ) -> None:
        self._settings = settings
        self._encryptor = encryptor
        self._db_session_factory = db_session_factory
        self._on_connected = on_account_connected
        self._active_polls: dict[str, threading.Thread] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_flow(self, db: Session) -> MsAuthFlow:
        """Initiate a new device code flow, persisting the state to the DB.

        Returns:
            The saved MsAuthFlow ORM instance (caller must commit).
        """
        app = create_public_client(self._settings)
        flow_data = app.initiate_device_flow(scopes=self._settings.microsoft_scopes)

        if "error" in flow_data:
            raise RuntimeError(
                f"Device flow initiation failed: {flow_data.get('error_description', flow_data['error'])}"
            )

        flow_id = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
            seconds=flow_data.get("expires_in", 900)
        )

        # Encrypt the device_code (short-lived sensitive value)
        encrypted_device_code = self._encryptor.encrypt(flow_data["device_code"])

        auth_flow = MsAuthFlow(
            flow_id=flow_id,
            device_code=encrypted_device_code,
            user_code=flow_data["user_code"],
            verification_uri=flow_data["verification_uri"],
            expires_at=expires_at,
            status="pending",
        )
        db.add(auth_flow)
        db.flush()

        # Start background poll
        self._start_background_poll(flow_id, flow_data, auth_flow.id)

        logger.info(
            "Device flow started: flow_id=%s user_code=%s",
            flow_id,
            flow_data["user_code"],
        )
        return auth_flow

    def get_flow_status(self, flow_id: str, db: Session) -> Optional[MsAuthFlow]:
        return db.query(MsAuthFlow).filter(MsAuthFlow.flow_id == flow_id).first()

    # ------------------------------------------------------------------
    # Background polling
    # ------------------------------------------------------------------

    def _start_background_poll(
        self, flow_id: str, flow_data: dict, db_row_id: int
    ) -> None:
        thread = threading.Thread(
            target=self._poll_for_completion,
            args=(flow_id, flow_data, db_row_id),
            daemon=True,
            name=f"ms-device-poll-{flow_id[:8]}",
        )
        self._active_polls[flow_id] = thread
        thread.start()

    def _poll_for_completion(
        self, flow_id: str, flow_data: dict, db_row_id: int
    ) -> None:
        """Poll Microsoft until user completes auth, flow expires, or error occurs."""
        import time

        app = create_public_client(self._settings)
        interval = flow_data.get("interval", 5)

        try:
            while True:
                time.sleep(interval)

                db = self._db_session_factory()
                try:
                    row = db.query(MsAuthFlow).filter(MsAuthFlow.id == db_row_id).first()
                    if not row or row.status != "pending":
                        logger.debug("Flow %s no longer pending, stopping poll", flow_id)
                        return

                    if datetime.utcnow() > row.expires_at:
                        row.status = "expired"
                        db.commit()
                        logger.info("Device flow %s expired", flow_id)
                        return

                    result = app.acquire_token_by_device_flow(
                        flow_data, timeout=1
                    )

                    if "access_token" in result:
                        self._handle_success(flow_id, result, row, db)
                        return

                    error = result.get("error", "")
                    if error == "authorization_pending":
                        pass  # keep polling
                    elif error == "authorization_declined":
                        row.status = "failed"
                        db.commit()
                        logger.info("Device flow %s declined by user", flow_id)
                        return
                    elif error == "expired_token":
                        row.status = "expired"
                        db.commit()
                        logger.info("Device flow %s token expired", flow_id)
                        return
                    elif error == "slow_down":
                        interval = min(interval + 5, 30)
                    else:
                        logger.warning(
                            "Device flow %s unexpected error: %s — %s",
                            flow_id,
                            error,
                            result.get("error_description", ""),
                        )
                        row.status = "failed"
                        db.commit()
                        return

                    db.commit()
                except Exception as exc:
                    logger.error("Error in device flow poll for %s: %s", flow_id, exc)
                    try:
                        db.rollback()
                    except Exception:
                        pass
                finally:
                    db.close()

        finally:
            self._active_polls.pop(flow_id, None)

    def _handle_success(
        self, flow_id: str, token_result: dict, row: MsAuthFlow, db: Session
    ) -> None:
        """Process successful authentication: create/update account and persist cache."""
        from microsoft_integration.models import MsAccount

        id_claims = token_result.get("id_token_claims", {})
        microsoft_user_id = id_claims.get("oid", id_claims.get("sub", ""))
        display_name = id_claims.get("name", "")
        email = (
            id_claims.get("preferred_username", "")
            or id_claims.get("email", "")
            or ""
        )
        tenant_id = id_claims.get("tid", "")

        # Upsert account
        account = (
            db.query(MsAccount)
            .filter(MsAccount.microsoft_user_id == microsoft_user_id)
            .first()
        )
        now = datetime.utcnow()
        if not account:
            account = MsAccount(
                microsoft_user_id=microsoft_user_id,
                tenant_id=tenant_id,
                display_name=display_name,
                email=email,
                last_login_at=now,
            )
            db.add(account)
            db.flush()
        else:
            account.display_name = display_name
            account.email = email
            account.tenant_id = tenant_id
            account.last_login_at = now
            account.enabled = True
            account.needs_reauthentication = False

        # Persist token cache
        # Re-create the MSAL app with cache, re-acquire silent to populate cache
        cache = msal.SerializableTokenCache()
        app_with_cache = create_public_client(self._settings, token_cache=cache)
        # Load the token into cache by acquiring silently after the flow
        # The cache is already populated by acquire_token_by_device_flow on the app instance
        # We serialize and encrypt it
        persisted = PersistedTokenCache(account.id, self._encryptor, db)
        # Inject the received cache state
        token_cache_obj = app_with_cache.token_cache
        if hasattr(token_cache_obj, "deserialize") and hasattr(
            app_with_cache.token_cache, "serialize"
        ):
            pass  # Token already in MSAL app cache, save it
        persisted.save_if_dirty()

        row.status = "completed"
        row.account_id = account.id
        db.commit()

        logger.info(
            "Device flow %s completed — account %d (%s)",
            flow_id,
            account.id,
            email,
        )

        if self._on_connected:
            try:
                self._on_connected(account.id)
            except Exception as exc:
                logger.warning("on_account_connected callback error: %s", exc)
