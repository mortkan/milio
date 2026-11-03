"""Health check routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from microsoft_integration.database import check_db_health, get_db
from microsoft_integration.schemas import HealthOut

router = APIRouter(prefix="/api/microsoft", tags=["Microsoft Health"])


@router.get("/health", response_model=HealthOut, summary="Service health check")
def health_check():
    from microsoft_integration.sync.scheduler import is_running as scheduler_is_running

    db_status = check_db_health()
    return HealthOut(
        status="ok" if db_status["database"] == "connected" else "degraded",
        database=db_status["database"],
        service="microsoft-integration",
        scheduler="running" if scheduler_is_running() else "stopped",
    )


@router.get(
    "/accounts/{account_id}/connection-test",
    summary="Test live Microsoft Graph connectivity for an account",
)
async def test_connection(account_id: int, db: Session = Depends(get_db)):
    """Verify the account can successfully reach Microsoft Graph (/me)."""
    from microsoft_integration.main import get_encryptor, get_settings
    from microsoft_integration.auth.token_cache import PersistedTokenCache
    from microsoft_integration.graph.client import GraphClient
    from microsoft_integration.graph.profile import get_my_profile
    from microsoft_integration.models import MsAccount

    account = db.query(MsAccount).filter(MsAccount.id == account_id).first()
    if not account:
        return {"status": "error", "detail": "Account not found"}

    settings = get_settings()
    encryptor = get_encryptor()

    try:
        persisted_cache = PersistedTokenCache(account_id, encryptor, db)
        async with GraphClient(settings, persisted_cache) as client:
            profile = await get_my_profile(client)
        return {
            "status": "ok",
            "display_name": profile.get("displayName"),
            "email": profile.get("mail") or profile.get("userPrincipalName"),
        }
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}
