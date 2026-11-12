from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.constants import STATUS_OPEN
from app.models.attendance import AttendanceBreak, AttendanceEvent, AttendanceSession


class AttendanceRepository:
    """Every read takes the owning user id, so records cannot cross employees."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def open_session(self, user_id: int, *, lock: bool = False) -> AttendanceSession | None:
        stmt = select(AttendanceSession).where(
            AttendanceSession.platform_user_id == user_id, AttendanceSession.status == STATUS_OPEN
        )
        if lock:
            stmt = stmt.with_for_update()
        return self.db.scalars(stmt).first()

    def owned_session(self, user_id: int, session_id: str) -> AttendanceSession | None:
        return self.db.scalars(
            select(AttendanceSession).where(AttendanceSession.id == session_id, AttendanceSession.platform_user_id == user_id)
        ).first()

    def session_by_check_in_request(self, user_id: int, request_id: str) -> AttendanceSession | None:
        return self.db.scalars(
            select(AttendanceSession).where(
                AttendanceSession.platform_user_id == user_id, AttendanceSession.check_in_request_id == request_id
            )
        ).first()

    def session_by_check_out_request(self, user_id: int, request_id: str) -> AttendanceSession | None:
        return self.db.scalars(
            select(AttendanceSession).where(
                AttendanceSession.platform_user_id == user_id, AttendanceSession.check_out_request_id == request_id
            )
        ).first()

    def _owned_break(self, user_id: int, *criteria) -> AttendanceBreak | None:
        return self.db.scalars(
            select(AttendanceBreak)
            .join(AttendanceSession, AttendanceBreak.session_id == AttendanceSession.id)
            .where(AttendanceSession.platform_user_id == user_id, *criteria)
        ).first()

    def break_by_start_request(self, user_id: int, request_id: str) -> AttendanceBreak | None:
        return self._owned_break(user_id, AttendanceBreak.start_request_id == request_id)

    def break_by_end_request(self, user_id: int, request_id: str) -> AttendanceBreak | None:
        return self._owned_break(user_id, AttendanceBreak.end_request_id == request_id)

    def latest_check_out(self, user_id: int) -> datetime | None:
        return self.db.scalars(
            select(AttendanceSession.check_out_at)
            .where(AttendanceSession.platform_user_id == user_id, AttendanceSession.check_out_at.is_not(None))
            .order_by(AttendanceSession.check_out_at.desc())
            .limit(1)
        ).first()

    def sessions_overlapping(self, user_id: int, start: datetime, end: datetime) -> list[AttendanceSession]:
        """Sessions with any part in ``[start, end)``, newest first."""
        return list(
            self.db.scalars(
                select(AttendanceSession)
                .where(
                    AttendanceSession.platform_user_id == user_id,
                    AttendanceSession.check_in_at < end,
                    or_(AttendanceSession.check_out_at.is_(None), AttendanceSession.check_out_at >= start),
                )
                .order_by(AttendanceSession.check_in_at.desc())
            )
        )

    def add_event(self, event: AttendanceEvent) -> None:
        self.db.add(event)
