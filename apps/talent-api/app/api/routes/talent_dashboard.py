from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, get_talent_scope, require_staff_scope
from app.db.session import get_db
from app.schemas.dashboard import ClientDashboardOut, TaDashboardOut
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/talent", tags=["talent-dashboard"])


@router.get("/dashboard/client", response_model=ClientDashboardOut)
def client_dashboard(
    scope: TalentScope = Depends(get_talent_scope), db: Session = Depends(get_db)
) -> ClientDashboardOut:
    if not scope.has("talent.dashboard.read_own") or scope.client_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Client dashboard requires a client persona")
    return DashboardService(db).client_dashboard(scope.client_id)


@router.get("/ta/dashboard", response_model=TaDashboardOut)
def ta_dashboard(
    scope: TalentScope = Depends(require_staff_scope), db: Session = Depends(get_db)
) -> TaDashboardOut:
    return DashboardService(db).ta_dashboard(allowed_client_ids=scope.client_ids)
