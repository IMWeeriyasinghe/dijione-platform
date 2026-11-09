"""Correction requests. Employees propose; only an approval changes official
records, atomically and with audit events. Originals are always preserved."""

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar

from auth_client_py.correlation import get_correlation_id
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm.exc import StaleDataError

from app.core.constants import (
    CORRECTION_AMEND,
    CORRECTION_APPROVED,
    CORRECTION_CREATE_MISSING,
    CORRECTION_PENDING,
    CORRECTION_REJECTED,
    CORRECTION_WITHDRAWN,
    STATUS_COMPLETED,
    STATUS_OPEN,
)
from app.core.errors import AttendanceError
from app.models.attendance import AttendanceBreak, AttendanceEvent, AttendanceSession
from app.models.corrections import AttendanceEmployee, CorrectionRequest
from app.schemas.corrections import CorrectionIn
from app.services.attendance_policy import AttendancePolicy
from app.services.attendance_service import Clock, system_clock

T = TypeVar("T")
Intervals = list[tuple[datetime, datetime]]
_MAX_ATTEMPTS = 8


def _secs(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(microsecond=0)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def snapshot(session: AttendanceSession) -> dict:
    return {
        "status": session.status,
        "work_mode": session.work_mode,
        "check_in_at": _iso(session.check_in_at),
        "check_out_at": _iso(session.check_out_at),
        "breaks": [{"started_at": _iso(b.started_at), "ended_at": _iso(b.ended_at)} for b in session.breaks],
    }


def _invalid(detail: str) -> AttendanceError:
    return AttendanceError("CORRECTION_INVALID", detail, 422)


class CorrectionService:
    def __init__(self, db: Session, policy: AttendancePolicy, clock: Clock = system_clock) -> None:
        self.db = db
        self.policy = policy
        self.clock = clock

    def now(self) -> datetime:
        return _secs(self.clock())

    def _retrying(self, work: Callable[[], T]) -> T:
        for tries in range(1, _MAX_ATTEMPTS + 1):
            try:
                result = work()
                self.db.commit()
                return result
            except AttendanceError:
                self.db.rollback()
                raise
            except (IntegrityError, StaleDataError):
                self.db.rollback()
            except OperationalError as exc:
                self.db.rollback()
                if "locked" not in str(exc.orig).lower() and "deadlock" not in str(exc.orig).lower():
                    raise
            time.sleep(0.02 * tries)
        raise AttendanceError("CONCURRENT_UPDATE", "Another change is in progress. Please try again.")

    def _event(
        self,
        actor: int,
        subject: int,
        action: str,
        entity_type: str,
        entity_id: str,
        session_id: str | None,
        at: datetime,
        before: dict | None,
        after: dict | None,
    ) -> None:
        self.db.add(
            AttendanceEvent(
                actor_user_id=actor,
                subject_user_id=subject,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                session_id=session_id,
                occurred_at=at,
                before_state=before,
                after_state=after,
                correlation_id=get_correlation_id(),
            )
        )

    def _validate(
        self,
        user_id: int,
        check_in: datetime,
        check_out: datetime | None,
        breaks: Intervals,
        exclude_session: str | None,
        now: datetime,
    ) -> None:
        if check_in > now:
            raise _invalid("Check-in cannot be in the future.")
        if check_out is not None and check_out > now:
            raise _invalid("Check-out cannot be in the future.")
        if check_out is not None and check_out < check_in:
            raise _invalid("Check-out must not be before check-in.")
        end = check_out or now
        previous: datetime | None = None
        for started, ended in sorted(breaks):
            if ended < started:
                raise _invalid("A break must not end before it starts.")
            if started < check_in or ended > end:
                raise _invalid("Breaks must fall within the session.")
            if previous is not None and started < previous:
                raise _invalid("Breaks must not overlap.")
            previous = ended
        stmt = (
            select(func.count())
            .select_from(AttendanceSession)
            .where(
                AttendanceSession.platform_user_id == user_id,
                AttendanceSession.check_in_at < end,
                or_(AttendanceSession.check_out_at.is_(None), AttendanceSession.check_out_at > check_in),
            )
        )
        if exclude_session:
            stmt = stmt.where(AttendanceSession.id != exclude_session)
        if self.db.scalar(stmt):
            raise AttendanceError("SESSION_OVERLAP", "These times overlap another attendance session.")

    def submit(self, user_id: int, body: CorrectionIn) -> tuple[CorrectionRequest, bool]:
        def work() -> tuple[CorrectionRequest, bool]:
            existing = self.db.scalars(
                select(CorrectionRequest).where(
                    CorrectionRequest.platform_user_id == user_id, CorrectionRequest.client_request_id == body.client_request_id
                )
            ).first()
            if existing is not None:
                return existing, True
            now = self.now()
            breaks: Intervals | None = (
                [(_secs(b.started_at), _secs(b.ended_at)) for b in body.breaks] if body.breaks is not None else None
            )
            session: AttendanceSession | None = None
            if body.session_id:
                session = self.db.get(AttendanceSession, body.session_id)
                if session is None or session.platform_user_id != user_id:
                    raise AttendanceError("SESSION_NOT_FOUND", "Attendance session not found.", 404)
                if self.db.scalar(
                    select(func.count())
                    .select_from(CorrectionRequest)
                    .where(CorrectionRequest.session_id == session.id, CorrectionRequest.status == CORRECTION_PENDING)
                ):
                    raise AttendanceError("CORRECTION_ALREADY_PENDING", "This session already has a pending correction request.")
                proposed = self._merge_amend(session, body, breaks)
                self._validate(
                    user_id,
                    _parse(proposed["check_in_at"]),
                    _parse(proposed["check_out_at"]),
                    self._intervals(proposed),
                    session.id,
                    now,
                )
                if proposed["work_mode"] != session.work_mode:
                    self.policy.ensure_mode_enabled(proposed["work_mode"])
                original = snapshot(session)
                if {k: original[k] for k in proposed} == proposed:
                    raise AttendanceError("CORRECTION_NO_CHANGES", "The proposed values match the current record.", 422)
            else:
                if body.work_mode is None or body.check_in_at is None or body.check_out_at is None:
                    raise _invalid("A missing session needs a work mode, check-in and check-out.")
                self.policy.ensure_mode_enabled(body.work_mode)
                proposed = {
                    "work_mode": body.work_mode,
                    "check_in_at": _iso(_secs(body.check_in_at)),
                    "check_out_at": _iso(_secs(body.check_out_at)),
                    "breaks": [{"started_at": _iso(a), "ended_at": _iso(b)} for a, b in sorted(breaks or [])],
                }
                self._validate(user_id, _secs(body.check_in_at), _secs(body.check_out_at), breaks or [], None, now)
                self._ensure_no_pending_overlap(user_id, _secs(body.check_in_at), _secs(body.check_out_at))
                original = None
            item = CorrectionRequest(
                platform_user_id=user_id,
                kind=CORRECTION_AMEND if session else CORRECTION_CREATE_MISSING,
                status=CORRECTION_PENDING,
                session_id=session.id if session else None,
                base_session_version=session.version if session else None,
                reason=body.reason.strip(),
                original=original,
                proposed=proposed,
                client_request_id=body.client_request_id,
            )
            self.db.add(item)
            self.db.flush()
            self._event(
                user_id, user_id, "CORRECTION_REQUESTED", "CorrectionRequest", item.id, item.session_id, now, original, proposed
            )
            return item, False

        return self._retrying(work)

    def _ensure_no_pending_overlap(self, user_id: int, start: datetime, end: datetime) -> None:
        pending = self.db.scalars(
            select(CorrectionRequest).where(
                CorrectionRequest.platform_user_id == user_id,
                CorrectionRequest.status == CORRECTION_PENDING,
                CorrectionRequest.kind == CORRECTION_CREATE_MISSING,
            )
        )
        for other in pending:
            if _parse(other.proposed["check_in_at"]) < end and _parse(other.proposed["check_out_at"]) > start:
                raise AttendanceError("CORRECTION_ALREADY_PENDING", "A pending request already covers these times.")

    @staticmethod
    def _intervals(proposed: dict) -> Intervals:
        return [(_parse(b["started_at"]), _parse(b["ended_at"])) for b in proposed["breaks"]]

    @staticmethod
    def _merge_amend(session: AttendanceSession, body: CorrectionIn, breaks: Intervals | None) -> dict:
        check_out = _secs(body.check_out_at) if body.check_out_at else session.check_out_at
        if breaks is None:
            if any(b.ended_at is None for b in session.breaks):
                raise _invalid("This session has an open break. Include an end time for it.")
            current = [{"started_at": _iso(b.started_at), "ended_at": _iso(b.ended_at)} for b in session.breaks]
        else:
            current = [{"started_at": _iso(a), "ended_at": _iso(b)} for a, b in sorted(breaks)]
        return {
            "work_mode": body.work_mode or session.work_mode,
            "check_in_at": _iso(_secs(body.check_in_at) if body.check_in_at else session.check_in_at),
            "check_out_at": _iso(check_out),
            "breaks": current,
        }

    def _load_for_decision(self, request_id: str, reviewer: int) -> CorrectionRequest:
        item = self.db.scalars(select(CorrectionRequest).where(CorrectionRequest.id == request_id).with_for_update()).first()
        if item is None:
            raise AttendanceError("CORRECTION_NOT_FOUND", "Correction request not found.", 404)
        if item.platform_user_id == reviewer:
            raise AttendanceError("SELF_DECISION_FORBIDDEN", "You cannot decide a correction to your own attendance.", 403)
        if item.status != CORRECTION_PENDING:
            raise AttendanceError("CORRECTION_NOT_PENDING", "This request has already been decided or withdrawn.")
        return item

    def _serialize_employee(self, user_id: int, now: datetime) -> None:
        """Two approvals for one employee cannot both pass the overlap check."""
        row = self.db.scalars(
            select(AttendanceEmployee).where(AttendanceEmployee.platform_user_id == user_id).with_for_update()
        ).first()
        if row is None:
            self.db.add(AttendanceEmployee(platform_user_id=user_id, full_name=f"User #{user_id}", last_seen_at=now))
        else:
            row.last_seen_at = now
            flag_modified(row, "last_seen_at")
        self.db.flush()

    def approve(self, request_id: str, reviewer: int, reviewer_name: str, note: str | None) -> CorrectionRequest:
        def work() -> CorrectionRequest:
            item = self._load_for_decision(request_id, reviewer)
            now = self.now()
            self._serialize_employee(item.platform_user_id, now)
            proposed = item.proposed
            check_in, check_out = _parse(proposed["check_in_at"]), _parse(proposed["check_out_at"])
            breaks = self._intervals(proposed)
            if item.kind == CORRECTION_AMEND:
                session = self.db.scalars(
                    select(AttendanceSession).where(AttendanceSession.id == item.session_id).with_for_update()
                ).first()
                if session.version != item.base_session_version:
                    raise AttendanceError(
                        "CORRECTION_STALE", "The session changed after this request was made. Reject it and ask for a new one."
                    )
                self._validate(item.platform_user_id, check_in, check_out, breaks, session.id, now)
                before = snapshot(session)
                self._apply_amend(session, item, reviewer, check_in, check_out, breaks, now)
                action = "SESSION_CORRECTED"
            else:
                self._validate(item.platform_user_id, check_in, check_out, breaks, None, now)
                before = None
                session = self._create_session(item, reviewer, check_in, check_out, breaks)
                item.session_id = session.id
                action = "SESSION_CREATED_BY_CORRECTION"
            self.db.flush()
            self.db.expire(session, ["breaks"])
            after = snapshot(session)
            item.status = CORRECTION_APPROVED
            self._decide(item, reviewer, reviewer_name, note, now)
            self.db.flush()
            self._event(reviewer, item.platform_user_id, action, "AttendanceSession", session.id, session.id, now, before, after)
            self._event(
                reviewer,
                item.platform_user_id,
                "CORRECTION_APPROVED",
                "CorrectionRequest",
                item.id,
                session.id,
                now,
                {"status": CORRECTION_PENDING},
                {"status": CORRECTION_APPROVED, "note": note},
            )
            return item

        return self._retrying(work)

    def _apply_amend(
        self,
        session: AttendanceSession,
        item: CorrectionRequest,
        reviewer: int,
        check_in: datetime,
        check_out: datetime | None,
        breaks: Intervals,
        now: datetime,
    ) -> None:
        session.work_mode = item.proposed["work_mode"]
        session.check_in_at = check_in
        session.check_out_at = check_out
        if check_out is not None and session.status == STATUS_OPEN:
            session.status = STATUS_COMPLETED
            session.check_out_request_id = f"corr-{item.id}"
        session.correction_count += 1
        session.updated_by_user_id = reviewer
        current = [(b.started_at, b.ended_at) for b in session.breaks]
        if current != sorted(breaks):
            for old in list(session.breaks):
                old.voided_at = now
                old.voided_by_correction_id = item.id
            self.db.flush()
            self._add_breaks(session.id, item.id, breaks)

    def _create_session(
        self, item: CorrectionRequest, reviewer: int, check_in: datetime, check_out: datetime, breaks: Intervals
    ) -> AttendanceSession:
        session = AttendanceSession(
            platform_user_id=item.platform_user_id,
            work_mode=item.proposed["work_mode"],
            status=STATUS_COMPLETED,
            check_in_at=check_in,
            check_out_at=check_out,
            time_zone=self.policy.business_time_zone,
            check_in_request_id=f"corr-{item.id}",
            check_out_request_id=f"corr-{item.id}",
            created_by_user_id=reviewer,
            updated_by_user_id=reviewer,
            origin="CORRECTION",
            correction_count=1,
        )
        self.db.add(session)
        self.db.flush()
        self._add_breaks(session.id, item.id, breaks)
        return session

    def _add_breaks(self, session_id: str, correction_id: str, breaks: Intervals) -> None:
        for index, (started, ended) in enumerate(sorted(breaks)):
            key = f"c{index}-{correction_id}"
            self.db.add(
                AttendanceBreak(
                    session_id=session_id, started_at=started, ended_at=ended, start_request_id=key, end_request_id=key
                )
            )

    @staticmethod
    def _decide(item: CorrectionRequest, reviewer: int, reviewer_name: str, note: str | None, now: datetime) -> None:
        item.reviewer_user_id = reviewer
        item.reviewer_name = reviewer_name
        item.reviewed_at = now
        item.decision_note = note

    def reject(self, request_id: str, reviewer: int, reviewer_name: str, reason: str) -> CorrectionRequest:
        def work() -> CorrectionRequest:
            item = self._load_for_decision(request_id, reviewer)
            now = self.now()
            item.status = CORRECTION_REJECTED
            self._decide(item, reviewer, reviewer_name, reason.strip(), now)
            self.db.flush()
            self._event(
                reviewer,
                item.platform_user_id,
                "CORRECTION_REJECTED",
                "CorrectionRequest",
                item.id,
                item.session_id,
                now,
                {"status": CORRECTION_PENDING},
                {"status": CORRECTION_REJECTED, "note": reason.strip()},
            )
            return item

        return self._retrying(work)

    def withdraw(self, request_id: str, user_id: int) -> CorrectionRequest:
        def work() -> CorrectionRequest:
            item = self.db.scalars(
                select(CorrectionRequest)
                .where(CorrectionRequest.id == request_id, CorrectionRequest.platform_user_id == user_id)
                .with_for_update()
            ).first()
            if item is None:
                raise AttendanceError("CORRECTION_NOT_FOUND", "Correction request not found.", 404)
            if item.status != CORRECTION_PENDING:
                raise AttendanceError("CORRECTION_NOT_PENDING", "Only pending requests can be withdrawn.")
            now = self.now()
            item.status = CORRECTION_WITHDRAWN
            self.db.flush()
            self._event(
                user_id,
                user_id,
                "CORRECTION_WITHDRAWN",
                "CorrectionRequest",
                item.id,
                item.session_id,
                now,
                {"status": CORRECTION_PENDING},
                {"status": CORRECTION_WITHDRAWN},
            )
            return item

        return self._retrying(work)
