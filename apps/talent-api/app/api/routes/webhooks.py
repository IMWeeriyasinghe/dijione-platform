import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.services.sync_service import SyncService

router = APIRouter(prefix="/api/talent/webhooks", tags=["webhooks"])
logger = logging.getLogger("app.api.routes.webhooks")


def _verify_lever_signature(payload: dict) -> None:
    """HMAC-SHA256 verification per Lever's documented scheme: signature =
    HMAC-SHA256(key=signing_token, msg=signing_token + str(triggeredAt)).

    Verification is only enforced when LEVER_WEBHOOK_SIGNING_SECRET is
    configured — this dev environment has no production webhook wired up
    yet (CLAUDE.md §60/§63), so an unset secret is a warning, not a reject.
    When the secret IS configured, a missing/invalid signature is rejected
    with 401 rather than silently accepted.
    """
    secret = get_settings().lever_webhook_signing_secret
    if not secret:
        logger.warning(
            "Lever webhook received with no LEVER_WEBHOOK_SIGNING_SECRET configured "
            "— signature not verified. Do not enable production Lever webhooks "
            "until this is configured."
        )
        return

    triggered_at = payload.get("triggeredAt")
    provided_signature = payload.get("signature")
    if not triggered_at or not provided_signature:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing webhook signature")

    expected = hmac.new(
        secret.encode("utf-8"), f"{secret}{triggered_at}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, str(provided_signature)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")


@router.post("/lever")
async def lever_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    """Receives Lever webhook deliveries. Signature verification is
    enforced when LEVER_WEBHOOK_SIGNING_SECRET is configured (see
    ``_verify_lever_signature``). Idempotency is always enforced via
    IntegrationEvent regardless of signature configuration."""
    payload = await request.json()
    _verify_lever_signature(payload)
    event = SyncService(db).process_lever_event(payload)
    db.commit()
    return {"event_id": event.id, "status": event.processing_status}


@router.post("/hubspot")
async def hubspot_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    payload = await request.json()
    event = SyncService(db).process_hubspot_event(payload)
    db.commit()
    return {"event_id": event.id, "status": event.processing_status}
