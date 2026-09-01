"""HubSpot webhook receiver — moved here from talent-api (Architecture
Completion Plan Wave F / §3). No HubSpot event currently drives a
mutation; idempotency via IntegrationEvent is always enforced.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.sync_service import SyncService

router = APIRouter(prefix="/api/commercial/webhooks", tags=["commercial-webhooks"])


@router.post("/hubspot")
async def hubspot_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    payload = await request.json()
    event = SyncService(db).process_hubspot_event(payload)
    db.commit()
    return {"event_id": event.id, "status": event.processing_status}
