"""Account management routes."""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from microsoft_integration.database import get_db
from microsoft_integration.models import MsAccount
from microsoft_integration.schemas import AccountOut

logger = logging.getLogger("microsoft.api.account_routes")

router = APIRouter(prefix="/api/microsoft/accounts", tags=["Microsoft Accounts"])


@router.get("", response_model=List[AccountOut], summary="List connected accounts")
def list_accounts(db: Session = Depends(get_db)):
    accounts = db.query(MsAccount).order_by(MsAccount.id).all()
    return [AccountOut.model_validate(a) for a in accounts]


@router.get("/{account_id}", response_model=AccountOut, summary="Get account details")
def get_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(MsAccount).filter(MsAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return AccountOut.model_validate(account)


@router.post("/{account_id}/disconnect", summary="Disconnect a Microsoft account")
def disconnect_account(account_id: int, db: Session = Depends(get_db)):
    """Disable the account and clear its token cache.

    By default this does NOT delete sync mappings or Milo data.
    """
    account = db.query(MsAccount).filter(MsAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    from microsoft_integration.auth.token_cache import delete_token_cache
    delete_token_cache(account_id, db)
    account.enabled = False
    db.commit()
    return {"message": f"Account {account_id} disconnected. Sync mappings preserved."}


@router.post("/{account_id}/reauthorize", summary="Mark account for re-authorization")
def reauthorize_account(account_id: int, db: Session = Depends(get_db)):
    account = db.query(MsAccount).filter(MsAccount.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    account.needs_reauthentication = True
    db.commit()
    return {"message": f"Account {account_id} marked for re-authorization. Start a new Device Code Flow."}
