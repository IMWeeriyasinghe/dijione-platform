from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, require_staff_scope
from app.core.config import get_settings
from app.core.constants import PostingClientMappingStatus
from app.db.session import get_db
from app.integrations.factory import get_hubspot_client, get_lever_client
from app.models.posting_client_mapping import PostingClientMapping
from app.repositories.integration_repo import IntegrationEventRepository
from app.services.lever_contact_application_sync_service import LeverContactApplicationSyncService

router = APIRouter(prefix="/api/talent/integrations", tags=["integrations"])


@router.get("/lever/status")
def lever_status(
    scope: TalentScope = Depends(require_staff_scope), db: Session = Depends(get_db)
) -> dict:
    settings = get_settings()
    client = get_lever_client()

    def _count(status_value: str) -> int:
        stmt = select(func.count()).select_from(PostingClientMapping).where(
            PostingClientMapping.status == status_value
        )
        return db.execute(stmt).scalar_one()

    return {
        "mode": settings.integrations_mode,
        "provider": "lever",
        "postings_available": len(client.list_postings()),
        "postings_mapped": _count(PostingClientMappingStatus.VERIFIED.value),
        "postings_unmapped": _count(PostingClientMappingStatus.UNMAPPED.value),
        "postings_rejected": _count(PostingClientMappingStatus.REJECTED.value),
        "read_only": True,
    }


@router.post("/lever/sync-opportunities")
def sync_lever_opportunities(
    limit: int = 100,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> dict:
    """Read-only reconciliation pull of Lever Opportunities/Contacts into
    Candidate + PostingApplication (never the client-owned Application/
    TalentRequest tables — see posting_application.py). ``limit`` defaults
    to a small, safe sample — this tenant has shown source counts in the
    hundreds of thousands, so an unbounded full-tenant pull is never the
    implicit default. Never assigns a client to anything synced."""
    result = LeverContactApplicationSyncService(db).sync_opportunities(limit=limit)
    db.commit()
    return result


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
