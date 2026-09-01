import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.services.webhook_service import WebhookService

router = APIRouter(prefix="/api/recruitment/webhooks", tags=["recruitment-webhooks"])
logger = logging.getLogger("recruitment-api.webhooks")


def _verify_lever_signature(payload: dict) -> None:
    """HMAC-SHA256 per Lever's scheme: HMAC(key=secret, msg=secret+triggeredAt).
    Enforced only when LEVER_WEBHOOK_SIGNING_SECRET is set — an unset secret
    is a warning, not a reject (no production webhook is wired up yet).
    Idempotency via IntegrationEvent is always enforced regardless.
    """
    secret = get_settings().lever_webhook_signing_secret
    if not secret:
        logger.warning(
            "Lever webhook received with no LEVER_WEBHOOK_SIGNING_SECRET — signature "
            "not verified. Do not enable production Lever webhooks until it is set."
        )
        return
    triggered_at = payload.get("triggeredAt")
    provided = payload.get("signature")
    if not triggered_at or not provided:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing webhook signature")
    expected = hmac.new(
        secret.encode(), f"{secret}{triggered_at}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, str(provided)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")


@router.post("/lever")
async def lever_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    payload = await request.json()
    _verify_lever_signature(payload)
    event = WebhookService(db).process_lever_event(payload)
    db.commit()
    return {"event_id": event.id, "status": event.processing_status}
