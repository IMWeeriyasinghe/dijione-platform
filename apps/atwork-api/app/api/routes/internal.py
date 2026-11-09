"""Called only by the scheduled job, with the internal service secret."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_internal_service
from app.api.routes.attendance import get_clock
from app.db.session import get_db
from app.services import notifications
from app.services.attendance_policy import AttendancePolicy, get_policy
from app.services.attendance_service import Clock

router = APIRouter(prefix="/api/atwork/internal", tags=["internal"], dependencies=[Depends(require_internal_service)])


@router.post("/notifications/run")
def run_notifications(
    db: Session = Depends(get_db), policy: AttendancePolicy = Depends(get_policy), clock: Clock = Depends(get_clock)
) -> dict:
    now = clock()
    queued = notifications.enqueue_scheduled(db, policy, now)
    return {"queued": queued, "delivery": notifications.deliver_pending(db, notifications.platform_client(), now)}
