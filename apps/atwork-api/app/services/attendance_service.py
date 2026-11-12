"""Attendance state transitions. Each change and its audit event commit together.

A request that loses a race is rolled back and evaluated again from committed
state, so it becomes either an idempotent replay or an accurate rejection.
"""

import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from auth_client_py.correlation import get_correlation_id
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from app.core.constants import STATUS_COMPLETED, STATUS_OPEN
from app.core.errors import AttendanceError
from app.models.attendance import AttendanceBreak, AttendanceEvent, AttendanceSession
from app.repositories.attendance_repository import AttendanceRepository
from app.services.attendance_policy import AttendancePolicy
from app.services.time_accounting import Totals, daily_totals, local_day_bounds

Clock = Callable[[], datetime]
Result = tuple[AttendanceSession, bool]

_MAX_ATTEMPTS = 8


def system_clock() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _session_state(session: AttendanceSession) -> dict:
    return {
        "status": session.status,
        "work_mode": session.work_mode,
        "check_in_at": _iso(session.check_in_at),
        "check_out_at": _iso(session.check_out_at),
    }


def _break_state(item: AttendanceBreak) -> dict:
    return {"started_at": _iso(item.started_at), "ended_at": _iso(item.ended_at)}


def open_break(session: AttendanceSession) -> AttendanceBreak | None:
    return next((item for item in session.breaks if item.ended_at is None), None)


def _is_transient_lock(exc: OperationalError) -> bool:
    message = str(exc.orig).lower()
    return "locked" in message or "deadlock" in message or "could not serialize" in message


class AttendanceService:
    def __init__(self, db: Session, policy: AttendancePolicy, clock: Clock = system_clock) -> None:
        self.db = db
        self.repo = AttendanceRepository(db)
        self.policy = policy
        self.clock = clock

    def now(self) -> datetime:
        return self.clock().astimezone(UTC).replace(microsecond=0)

    def _transaction(self, replay: Callable[[], Result | None], attempt: Callable[[], Result]) -> Result:
        for tries in range(1, _MAX_ATTEMPTS + 1):
            try:
                result = replay() or attempt()
                self.db.commit()
                return result
            except AttendanceError:
                # A duplicate of this request may have committed after the
                # lookup above; it must replay rather than be rejected.
                self.db.rollback()
                result = replay()
                if result is None:
                    raise
                return result
            except (IntegrityError, StaleDataError):
                self.db.rollback()
            except OperationalError as exc:
                self.db.rollback()
                if not _is_transient_lock(exc):
                    raise
            time.sleep(0.02 * tries)
        raise AttendanceError("CONCURRENT_UPDATE", "Another attendance change is in progress. Please try again.")

    def _record(
        self,
        *,
        user_id: int,
        action: str,
        entity_type: str,
        entity_id: str,
        session: AttendanceSession,
        at: datetime,
        before: dict | None,
        after: dict,
        request_id: str,
    ) -> None:
        self.repo.add_event(
            AttendanceEvent(
                actor_user_id=user_id,
                subject_user_id=session.platform_user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                session_id=session.id,
                occurred_at=at,
                before_state=before,
                after_state=after,
                request_id=request_id,
                correlation_id=get_correlation_id(),
            )
        )

    @staticmethod
    def _ensure_not_before(now: datetime, floor: datetime | None) -> None:
        """Timestamps are never adjusted: a clock behind the record is rejected."""
        if floor is not None and now < floor:
            raise AttendanceError(
                "TIMELINE_CONFLICT", "The server time is behind your latest attendance record. Please try again."
            )

    def _require_open(self, user_id: int) -> AttendanceSession:
        session = self.repo.open_session(user_id, lock=True)
        if session is None:
            raise AttendanceError("NOT_CHECKED_IN", "You are not checked in.")
        return session

    @staticmethod
    def _touch(session: AttendanceSession, user_id: int, now: datetime) -> None:
        # Always dirties the row, so version checks serialize every change to a session.
        session.updated_by_user_id = user_id
        session.updated_at = max(datetime.now(UTC), session.updated_at + timedelta(microseconds=1), now)

    def check_in(self, user_id: int, work_mode: str, request_id: str) -> Result:
        def replay() -> Result | None:
            existing = self.repo.session_by_check_in_request(user_id, request_id)
            if existing is None:
                return None
            if existing.work_mode != work_mode:
                raise AttendanceError("IDEMPOTENCY_CONFLICT", "This request ID was already used with a different work mode.")
            return existing, True

        def attempt() -> Result:
            self.policy.ensure_mode_enabled(work_mode)
            if self.repo.open_session(user_id) is not None:
                raise AttendanceError("ALREADY_CHECKED_IN", "You are already checked in.")
            now = self.now()
            self._ensure_not_before(now, self.repo.latest_check_out(user_id))
            session = AttendanceSession(
                platform_user_id=user_id,
                work_mode=work_mode,
                status=STATUS_OPEN,
                check_in_at=now,
                time_zone=self.policy.business_time_zone,
                check_in_request_id=request_id,
                created_by_user_id=user_id,
                updated_by_user_id=user_id,
            )
            self.db.add(session)
            self.db.flush()
            self._record(
                user_id=user_id,
                action="CHECK_IN",
                entity_type="AttendanceSession",
                entity_id=session.id,
                session=session,
                at=now,
                before=None,
                after=_session_state(session),
                request_id=request_id,
            )
            return session, False

        return self._transaction(replay, attempt)

    def start_break(self, user_id: int, request_id: str) -> Result:
        def replay() -> Result | None:
            existing = self.repo.break_by_start_request(user_id, request_id)
            return (existing.session, True) if existing is not None else None

        def attempt() -> Result:
            session = self._require_open(user_id)
            if open_break(session) is not None:
                raise AttendanceError("BREAK_ALREADY_ACTIVE", "You are already on a break.")
            now = self.now()
            ends = [item.ended_at for item in session.breaks if item.ended_at]
            self._ensure_not_before(now, max([session.check_in_at, *ends]))
            item = AttendanceBreak(session=session, started_at=now, start_request_id=request_id)
            self.db.add(item)
            self._touch(session, user_id, now)
            self.db.flush()
            self._record(
                user_id=user_id,
                action="BREAK_START",
                entity_type="AttendanceBreak",
                entity_id=item.id,
                session=session,
                at=now,
                before=None,
                after=_break_state(item),
                request_id=request_id,
            )
            return session, False

        return self._transaction(replay, attempt)

    def end_break(self, user_id: int, request_id: str) -> Result:
        def replay() -> Result | None:
            existing = self.repo.break_by_end_request(user_id, request_id)
            return (existing.session, True) if existing is not None else None

        def attempt() -> Result:
            session = self._require_open(user_id)
            item = open_break(session)
            if item is None:
                raise AttendanceError("NO_ACTIVE_BREAK", "You are not on a break.")
            now = self.now()
            self._ensure_not_before(now, item.started_at)
            before = _break_state(item)
            item.ended_at = now
            item.end_request_id = request_id
            self._touch(session, user_id, now)
            self.db.flush()
            self._record(
                user_id=user_id,
                action="BREAK_END",
                entity_type="AttendanceBreak",
                entity_id=item.id,
                session=session,
                at=now,
                before=before,
                after=_break_state(item),
                request_id=request_id,
            )
            return session, False

        return self._transaction(replay, attempt)

    def check_out(self, user_id: int, request_id: str) -> Result:
        def replay() -> Result | None:
            existing = self.repo.session_by_check_out_request(user_id, request_id)
            return (existing, True) if existing is not None else None

        def attempt() -> Result:
            session = self._require_open(user_id)
            self.policy.ensure_can_check_out(session)
            now = self.now()
            ends = [item.ended_at for item in session.breaks if item.ended_at]
            self._ensure_not_before(now, max([session.check_in_at, *ends]))
            before = _session_state(session)
            session.status = STATUS_COMPLETED
            session.check_out_at = now
            session.check_out_request_id = request_id
            self._touch(session, user_id, now)
            self.db.flush()
            self._record(
                user_id=user_id,
                action="CHECK_OUT",
                entity_type="AttendanceSession",
                entity_id=session.id,
                session=session,
                at=now,
                before=before,
                after=_session_state(session),
                request_id=request_id,
            )
            return session, False

        return self._transaction(replay, attempt)

    def current(self, user_id: int) -> AttendanceSession | None:
        return self.repo.open_session(user_id)

    def owned_session(self, user_id: int, session_id: str) -> AttendanceSession:
        session = self.repo.owned_session(user_id, session_id)
        if session is None:
            raise AttendanceError("SESSION_NOT_FOUND", "Attendance session not found.", 404)
        return session

    def local_date(self, now: datetime) -> date:
        return now.astimezone(self.policy.zone).date()

    def sessions_for_range(self, user_id: int, date_from: date, date_to: date) -> list[AttendanceSession]:
        zone = self.policy.zone
        return self.repo.sessions_overlapping(user_id, local_day_bounds(date_from, zone)[0], local_day_bounds(date_to, zone)[1])

    def daily(self, sessions: list[AttendanceSession], now: datetime) -> dict[date, Totals]:
        return daily_totals(sessions, self.policy.zone, now, self.policy.unverified_after_seconds)
