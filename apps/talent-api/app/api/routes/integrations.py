from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, require_staff_scope
from app.core.config import get_settings
from app.db.session import get_db
from app.integrations.factory import get_hubspot_client, get_lever_client
from app.repositories.integration_repo import IntegrationEventRepository

router = APIRouter(prefix="/api/talent/integrations", tags=["integrations"])


@router.get("/lever/status")
def lever_status(scope: TalentScope = Depends(require_staff_scope)) -> dict:
    settings = get_settings()
    client = get_lever_client()
    return {
        "mode": settings.integrations_mode,
        "provider": "lever",
        "postings_available": len(client.list_postings()),
        "read_only": True,
    }


@router.get("/hubspot/status")
def hubspot_status(scope: TalentScope = Depends(require_staff_scope)) -> dict:
    settings = get_settings()
    client = get_hubspot_client()
    return {
        "mode": settings.integrations_mode,
        "provider": "hubspot",
        "companies_available": len(client.list_companies()),
        "read_only": True,
    }


@router.get("/events")
def recent_events(
    scope: TalentScope = Depends(require_staff_scope), db: Session = Depends(get_db)
) -> list[dict]:
    events = IntegrationEventRepository(db).list_recent()
    return [
        {
            "id": e.id,
            "provider": e.provider,
            "event_type": e.event_type,
            "processing_status": e.processing_status,
            "received_at": e.received_at.isoformat(),
        }
        for e in events
    ]
