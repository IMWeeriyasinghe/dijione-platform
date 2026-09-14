from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import OrderIssueStatus, OrderStatus
from app.models.birthday_order import BirthdayOrder
from app.models.order_issue import OrderIssue
from app.services.order_status_service import SUPPLIER_VISIBLE_STATUSES

# Orders whose *fulfilment* is settled — excluded from due=today/tomorrow/
# overdue, verify=overdue, acceptance=*, and every dashboard "is this order
# still actionable" count. This is the single shared source of truth for
# that question (Phase 1.6 §4) — do not re-declare a local copy elsewhere;
# every prior duplicate (count_overdue_delivery's own tuple, portal.py's
# due-counts, which had drifted to omit UNABLE_TO_FULFIL) has been removed
# in favour of importing this one.
#
# This is NOT the same concept as "communication is closed" (Phase 1.6
# review correction #1) — see order_status_service.SUPPLIER_COMMUNICATION_CLOSED_STATUSES
# for that narrower, separately-named set.
_TERMINAL_STATUSES = (
    OrderStatus.DELIVERED.value, OrderStatus.COMPLETED.value,
    OrderStatus.CANCELLED.value, OrderStatus.UNABLE_TO_FULFIL.value,
)


def _apply_due(stmt, due: str | None, *, today: date | None = None):
    """Delivery-window filter shared by the internal and supplier lists
    (Phase 1.5 §F/§G): 'today' | 'tomorrow' | 'overdue', non-terminal only."""
    if not due:
        return stmt
    today = today or date.today()
    stmt = stmt.where(
        BirthdayOrder.delivery_date.is_not(None),
        BirthdayOrder.status.notin_(_TERMINAL_STATUSES),
    )
    if due == "today":
        return stmt.where(BirthdayOrder.delivery_date == today)
    if due == "tomorrow":
        return stmt.where(BirthdayOrder.delivery_date == today + timedelta(days=1))
    if due == "overdue":
        return stmt.where(BirthdayOrder.delivery_date < today)
    return stmt


def _apply_has_open_issue(stmt, has_open_issue: bool | None):
    if has_open_issue is None:
        return stmt
    sub = select(OrderIssue.order_id).where(OrderIssue.status == OrderIssueStatus.OPEN.value)
    return stmt.where(
        BirthdayOrder.id.in_(sub) if has_open_issue else BirthdayOrder.id.notin_(sub)
    )


def _apply_verify(stmt, verify: str | None, *, today: date | None = None):
    """Phase 1.6 §7 (R8): the exact predicate behind the "Verification
    overdue" dashboard card, now also reachable as a list filter so the
    card's link is never a superset of what it counts. Only 'overdue' is
    defined today — the same shape as _apply_due, on purpose."""
    if not verify:
        return stmt
    today = today or date.today()
    if verify == "overdue":
        return stmt.where(
            BirthdayOrder.status == OrderStatus.PENDING_VERIFICATION.value,
            BirthdayOrder.verify_by.is_not(None),
            BirthdayOrder.verify_by < today,
        )
    return stmt


def _apply_completed(stmt, completed: str | None, *, today: date | None = None):
    """Phase 1.6 §11/§13 (R17): the supplier 'Completed today' card's exact
    predicate, also reachable as a list filter — never the broader
    'status in (DELIVERED, COMPLETED)' the card used to link to."""
    if not completed:
        return stmt
    today = today or date.today()
    if completed == "today":
        return stmt.where(
            BirthdayOrder.status == OrderStatus.COMPLETED.value,
            func.date(BirthdayOrder.completed_at) == today,
        )
    return stmt


def _apply_acceptance(stmt, acceptance: str | None, *, sla_cutoff: datetime | None = None):
    """Phase 1.6 §6 (R6): 'awaiting' (every SENT_TO_SUPPLIER order) vs.
    'overdue' (SENT_TO_SUPPLIER past the acknowledgement SLA). The SLA
    cutoff is always computed server-side by the caller from
    BirthdayDetectionConfig — the frontend only ever sends the word
    'awaiting'/'overdue', never a raw timestamp (review correction #4)."""
    if not acceptance:
        return stmt
    stmt = stmt.where(BirthdayOrder.status == OrderStatus.SENT_TO_SUPPLIER.value)
    if acceptance == "awaiting":
        return stmt
    if acceptance == "overdue":
        cutoff = sla_cutoff or datetime.now(UTC)
        return stmt.where(
            BirthdayOrder.released_at.is_not(None),
            BirthdayOrder.released_at < cutoff,
        )
    return stmt


_SORTABLE_COLUMNS = {
    "employee_number": BirthdayOrder.employee_number,
    "employee_id": BirthdayOrder.employee_id,
    "employee_name": BirthdayOrder.employee_name,
    "birthday_date": BirthdayOrder.birthday_date,
    "delivery_date": BirthdayOrder.delivery_date,
    "status": BirthdayOrder.status,
    "created_at": BirthdayOrder.created_at,
    "supplier_id": BirthdayOrder.supplier_id,
}


class BirthdayOrderRepository:
    """All read/write access to BirthdayOrder goes through here. Full
    CRUD (filtering, hold/release/cancel transitions, etc.) is Phase C/D's
    job — this is the minimal surface Phase A needs."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, order_id: int) -> BirthdayOrder | None:
        return self.db.get(BirthdayOrder, order_id)

    def get_by_employee_and_year(self, employee_id: str, birthday_year: int) -> BirthdayOrder | None:
        stmt = select(BirthdayOrder).where(
            BirthdayOrder.employee_id == employee_id,
            BirthdayOrder.birthday_year == birthday_year,
        )
        return self.db.execute(stmt).scalars().first()

    def list(self) -> list[BirthdayOrder]:
        stmt = select(BirthdayOrder).order_by(BirthdayOrder.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def create(self, order: BirthdayOrder) -> BirthdayOrder:
        self.db.add(order)
        self.db.flush()
        return order

    @staticmethod
    def _filtered_stmt(
        *,
        status: str | None = None,
        lead_time_class: str | None = None,
        office_location: str | None = None,
        supplier_id: int | None = None,
        search: str | None = None,
        address_verification_status: str | None = None,
        due: str | None = None,
        has_open_issue: bool | None = None,
        verify: str | None = None,
        acceptance: str | None = None,
        sla_cutoff: datetime | None = None,
    ):
        stmt = select(BirthdayOrder)
        stmt = _apply_due(stmt, due)
        stmt = _apply_has_open_issue(stmt, has_open_issue)
        stmt = _apply_verify(stmt, verify)
        stmt = _apply_acceptance(stmt, acceptance, sla_cutoff=sla_cutoff)
        if status is not None:
            # Comma-separated statuses supported for the Cake Orders saved
            # views (Phase 1 §1.7) — a single value still works unchanged.
            wanted = [s.strip() for s in status.split(",") if s.strip()]
            if len(wanted) == 1:
                stmt = stmt.where(BirthdayOrder.status == wanted[0])
            elif wanted:
                stmt = stmt.where(BirthdayOrder.status.in_(wanted))
        if lead_time_class is not None:
            stmt = stmt.where(BirthdayOrder.lead_time_class == lead_time_class)
        if office_location is not None:
            stmt = stmt.where(BirthdayOrder.office_location == office_location)
        if supplier_id is not None:
            stmt = stmt.where(BirthdayOrder.supplier_id == supplier_id)
        if address_verification_status is not None:
            stmt = stmt.where(BirthdayOrder.address_verification_status == address_verification_status)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(
                    BirthdayOrder.employee_number.ilike(like),
                    BirthdayOrder.employee_id.ilike(like),
                    BirthdayOrder.employee_name.ilike(like),
                    BirthdayOrder.order_reference.ilike(like),
                )
            )
        return stmt

    def list_filtered(
        self,
        *,
        status: str | None = None,
        lead_time_class: str | None = None,
        office_location: str | None = None,
        supplier_id: int | None = None,
        search: str | None = None,
        address_verification_status: str | None = None,
        due: str | None = None,
        has_open_issue: bool | None = None,
        verify: str | None = None,
        acceptance: str | None = None,
        sla_cutoff: datetime | None = None,
        sort_by: str | None = None,
        sort_direction: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[BirthdayOrder]:
        stmt = self._filtered_stmt(
            status=status, lead_time_class=lead_time_class,
            office_location=office_location, supplier_id=supplier_id,
            search=search, address_verification_status=address_verification_status,
            due=due, has_open_issue=has_open_issue,
            verify=verify, acceptance=acceptance, sla_cutoff=sla_cutoff,
        )
        column = _SORTABLE_COLUMNS.get(sort_by or "", BirthdayOrder.created_at)
        stmt = stmt.order_by(column.desc() if sort_direction == "desc" else column.asc())
        stmt = stmt.limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())

    def count_filtered(
        self,
        *,
        status: str | None = None,
        lead_time_class: str | None = None,
        office_location: str | None = None,
        supplier_id: int | None = None,
        search: str | None = None,
        address_verification_status: str | None = None,
        due: str | None = None,
        has_open_issue: bool | None = None,
        verify: str | None = None,
        acceptance: str | None = None,
        sla_cutoff: datetime | None = None,
    ) -> int:
        stmt = self._filtered_stmt(
            status=status, lead_time_class=lead_time_class,
            office_location=office_location, supplier_id=supplier_id,
            search=search, address_verification_status=address_verification_status,
            verify=verify, acceptance=acceptance, sla_cutoff=sla_cutoff,
            due=due, has_open_issue=has_open_issue,
        )
        count_stmt = select(func.count()).select_from(stmt.subquery())
        return self.db.execute(count_stmt).scalar_one()

    # -- Supplier-portal (Phase-Next §5) -------------------------------
    # ``supplier_id`` here always comes from the caller's own SupplierScope
    # claim, never from a request parameter — see app/api/routes/portal.py.
    # A visible order must additionally have actually been sent
    # (SENT_TO_SUPPLIER or later, i.e. not still DRAFT/pending internal
    # approval) — a supplier must never see an order before it's approved
    # and sent.
    # Includes terminal states (CANCELLED) so a cancelled order shows the
    # supplier a tombstone with a reason instead of silently 404-ing —
    # plan §Y "internal->supplier changes must not be silent".
    _SUPPLIER_VISIBLE_STATUSES = SUPPLIER_VISIBLE_STATUSES

    def _supplier_scoped_stmt(
        self, *, supplier_id: int, search: str | None = None,
        status_filter: str | None = None, due: str | None = None,
        has_open_issue: bool | None = None, completed: str | None = None,
    ):
        stmt = select(BirthdayOrder).where(
            BirthdayOrder.supplier_id == supplier_id,
            BirthdayOrder.status.in_(self._SUPPLIER_VISIBLE_STATUSES),
        )
        if status_filter:
            wanted = [s.strip() for s in status_filter.split(",") if s.strip()]
            if len(wanted) == 1:
                stmt = stmt.where(BirthdayOrder.status == wanted[0])
            elif wanted:
                stmt = stmt.where(BirthdayOrder.status.in_(wanted))
        stmt = _apply_due(stmt, due)
        stmt = _apply_has_open_issue(stmt, has_open_issue)
        stmt = _apply_completed(stmt, completed)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(BirthdayOrder.order_reference.ilike(like), BirthdayOrder.employee_name.ilike(like))
            )
        return stmt

    def list_for_supplier(
        self, *, supplier_id: int, search: str | None = None,
        status_filter: str | None = None, due: str | None = None,
        has_open_issue: bool | None = None, completed: str | None = None,
        sort_by: str | None = None, sort_direction: str = "desc",
        limit: int = 20, offset: int = 0,
    ) -> list[BirthdayOrder]:
        stmt = self._supplier_scoped_stmt(
            supplier_id=supplier_id, search=search, status_filter=status_filter, due=due,
            has_open_issue=has_open_issue, completed=completed,
        )
        column = _SORTABLE_COLUMNS.get(sort_by or "", BirthdayOrder.delivery_date)
        stmt = stmt.order_by(column.desc() if sort_direction == "desc" else column.asc())
        stmt = stmt.limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())

    def count_for_supplier(
        self, *, supplier_id: int, search: str | None = None,
        status_filter: str | None = None, due: str | None = None,
        has_open_issue: bool | None = None, completed: str | None = None,
    ) -> int:
        stmt = self._supplier_scoped_stmt(
            supplier_id=supplier_id, search=search, status_filter=status_filter, due=due,
            has_open_issue=has_open_issue, completed=completed,
        )
        count_stmt = select(func.count()).select_from(stmt.subquery())
        return self.db.execute(count_stmt).scalar_one()

    def get_for_supplier(self, order_id: int, *, supplier_id: int) -> BirthdayOrder | None:
        """Returns None (never the order) if the order belongs to a
        different supplier — a manipulated order id must 404, not 403,
        so an unauthorized caller learns nothing about whether the id
        exists at all."""
        order = self.db.get(BirthdayOrder, order_id)
        if order is None or order.supplier_id != supplier_id:
            return None
        if order.status not in self._SUPPLIER_VISIBLE_STATUSES:
            return None
        return order

    # -- Attention / exception / dashboard aggregates (plan §L/§M) -------

    def count_pending_verification(self) -> int:
        stmt = select(func.count()).select_from(BirthdayOrder).where(
            BirthdayOrder.status == OrderStatus.PENDING_VERIFICATION.value
        )
        return self.db.execute(stmt).scalar_one()

    def count_verification_overdue(self, *, today: date | None = None) -> int:
        stmt = _apply_verify(select(func.count()).select_from(BirthdayOrder), "overdue", today=today)
        return self.db.execute(stmt).scalar_one()

    def count_requires_review(self) -> int:
        stmt = select(func.count()).select_from(BirthdayOrder).where(
            BirthdayOrder.status == OrderStatus.REQUIRES_REVIEW.value
        )
        return self.db.execute(stmt).scalar_one()

    def count_requires_attention(self) -> int:
        stmt = select(func.count()).select_from(BirthdayOrder).where(
            BirthdayOrder.status == OrderStatus.REQUIRES_ATTENTION.value
        )
        return self.db.execute(stmt).scalar_one()

    def count_on_hold(self) -> int:
        stmt = select(func.count()).select_from(BirthdayOrder).where(
            BirthdayOrder.status == OrderStatus.ON_HOLD.value
        )
        return self.db.execute(stmt).scalar_one()

    def count_overdue_delivery(self, *, today: date | None = None) -> int:
        # Reference implementation (Phase 1.6 §4/§7) — count and every
        # "due=overdue" list filter share this exact predicate via
        # _apply_due, so this card can never drift from its own link.
        stmt = _apply_due(select(func.count()).select_from(BirthdayOrder), "overdue", today=today)
        return self.db.execute(stmt).scalar_one()

    def count_acceptance_awaiting(self) -> int:
        """Phase 1.6 §6 (R6) — every SENT_TO_SUPPLIER order, no SLA gate.
        Replaces the old, misleadingly-named single 'not accepted' card:
        this one increments the instant an order is released."""
        stmt = _apply_acceptance(select(func.count()).select_from(BirthdayOrder), "awaiting")
        return self.db.execute(stmt).scalar_one()

    def count_acceptance_overdue(self, *, sla_cutoff: datetime) -> int:
        """Renamed from count_supplier_not_accepted (Phase 1.6 §6) — same
        predicate, honest name: SENT_TO_SUPPLIER *and* past the SLA."""
        stmt = _apply_acceptance(select(func.count()).select_from(BirthdayOrder), "overdue", sla_cutoff=sla_cutoff)
        return self.db.execute(stmt).scalar_one()

    def count_deliveries_today_at_risk(self, *, today: date | None = None) -> int:
        # Phase 1.6 §7 (R7): was a hand-picked status allow-list that
        # excluded OUT_FOR_DELIVERY while the "due=today" list filter
        # (_apply_due) included it — the two disagreed. Now identical.
        stmt = _apply_due(select(func.count()).select_from(BirthdayOrder), "today", today=today)
        return self.db.execute(stmt).scalar_one()

    def list_upcoming(self, *, days_ahead: int) -> list[BirthdayOrder]:
        today = date.today()
        cutoff = today + timedelta(days=days_ahead)
        stmt = (
            select(BirthdayOrder)
            .where(BirthdayOrder.birthday_date >= today, BirthdayOrder.birthday_date <= cutoff)
            .order_by(BirthdayOrder.birthday_date.asc())
        )
        return list(self.db.execute(stmt).scalars().all())
