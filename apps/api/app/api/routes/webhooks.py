from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.sync_service import SyncService

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/lever")
async def lever_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    """Receives Lever webhook deliveries. Signature validation is a Phase G
    production-hardening item (CLAUDE.md §63) — not wired up without live
    Lever credentials to validate against. Idempotency is enforced
    regardless via IntegrationEvent."""
    payload = await request.json()
    event = SyncService(db).process_lever_event(payload)
    db.commit()
    return {"event_id": event.id, "status": event.processing_status}


@router.post("/hubspot")
async def hubspot_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    payload = await request.json()
    event = SyncService(db).process_hubspot_event(payload)
    db.commit()
    return {"event_id": event.id, "status": event.processing_status}
