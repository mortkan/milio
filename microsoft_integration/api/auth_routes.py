"""Authentication routes: Device Code Flow and future Auth Code + PKCE."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from microsoft_integration.database import get_db
from microsoft_integration.models import MsAuthFlow
from microsoft_integration.schemas import DeviceFlowStartOut, DeviceFlowStatusOut, AccountOut

logger = logging.getLogger("microsoft.api.auth_routes")

router = APIRouter(prefix="/api/microsoft/auth", tags=["Microsoft Auth"])


def _get_device_flow_manager():
    """Dependency injection for DeviceFlowManager (set at app startup)."""
    from microsoft_integration.main import get_device_flow_manager
    return get_device_flow_manager()


@router.post("/device/start", response_model=DeviceFlowStartOut, summary="Start Device Code Flow")
async def start_device_flow(
    db: Session = Depends(get_db),
    dfm=Depends(_get_device_flow_manager),
):
    """Initiate a new OAuth 2.0 Device Code Flow.

    Returns a user_code and verification_uri that the user opens in a browser.
    The backend polls Microsoft in the background for completion.
    """
    try:
        flow = dfm.start_flow(db)
        db.commit()
        return DeviceFlowStartOut(
            flow_id=flow.flow_id,
            user_code=flow.user_code,
            verification_uri=flow.verification_uri,
            message=(
                f"Open {flow.verification_uri} in a browser and enter code: {flow.user_code}"
            ),
            expires_at=flow.expires_at,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Device flow start error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to start authentication flow")


@router.get(
    "/device/{flow_id}/status",
    response_model=DeviceFlowStatusOut,
    summary="Check Device Code Flow status",
)
async def get_device_flow_status(
    flow_id: str,
    db: Session = Depends(get_db),
    dfm=Depends(_get_device_flow_manager),
):
    """Poll the status of an in-progress Device Code Flow."""
    flow = dfm.get_flow_status(flow_id, db)
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    account_out: Optional[AccountOut] = None
    if flow.status == "completed" and flow.account_id:
        from microsoft_integration.models import MsAccount
        account = db.query(MsAccount).filter(MsAccount.id == flow.account_id).first()
        if account:
            account_out = AccountOut.model_validate(account)

    return DeviceFlowStatusOut(
        flow_id=flow_id,
        status=flow.status,
        account=account_out,
    )
