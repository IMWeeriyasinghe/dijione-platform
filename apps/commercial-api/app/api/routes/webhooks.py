"""HubSpot webhook receiver — moved here from talent-api (Architecture
Completion Plan Wave F / §3). No HubSpot event currently drives a
mutation; idempotency via IntegrationEvent is always enforced.
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.services.sync_service import SyncService

router = APIRouter(prefix="/api/commercial/webhooks", tags=["commercial-webhooks"])
logger = logging.getLogger("commercial-api.webhooks")


def _verify_hubspot_signature(raw_body: bytes, provided: str | None) -> None:
    """Pre-shared-secret placeholder (see Settings.hubspot_webhook_secret's
    docstring) — not HubSpot's official v3 scheme. An unset secret is
    tolerated (warn, accept) only in app_env=development, mirroring
    recruitment-api's Lever webhook gate; outside development it fails
    closed (503) rather than silently accepting unauthenticated payloads.
    """
    settings = get_settings()
    secret = settings.hubspot_webhook_secret
    if not secret:
        if settings.app_env != "development":
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "HubSpot webhook secret is not configured for this environment",
            )
        logger.warning(
            "HubSpot webhook received with no HUBSPOT_WEBHOOK_SECRET — signature "
            "not verified (app_env=development only)."
        )
        return
    if not provided:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing webhook signature")
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, provided):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")


@router.post("/hubspot")
async def hubspot_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    raw_body = await request.body()
    _verify_hubspot_signature(raw_body, request.headers.get("X-Hub-Signature"))
    payload = await request.json()
    event = SyncService(db).process_hubspot_event(payload)
    db.commit()
    return {"event_id": event.id, "status": event.processing_status}
