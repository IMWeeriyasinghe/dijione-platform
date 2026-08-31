"""HubSpot webhook receiver. The Lever webhook moved to recruitment-api
with the rest of the Recruitment Source domain. HubSpot signature
verification will be added when the Commercial/CRM domain acquires live
access (Wave F relocates this route there).
"""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.sync_service import SyncService

router = APIRouter(prefix="/api/talent/webhooks", tags=["webhooks"])
logger = logging.getLogger("app.api.routes.webhooks")


@router.post("/hubspot")
async def hubspot_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    payload = await request.json()
    event = SyncService(db).process_hubspot_event(payload)
    db.commit()
    return {"event_id": event.id, "status": event.processing_status}
