from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.birthday_order import BirthdayOrder

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
    ):
        stmt = select(BirthdayOrder)
        if status is not None:
            stmt = stmt.where(BirthdayOrder.status == status)
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
        sort_by: str | None = None,
        sort_direction: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[BirthdayOrder]:
        stmt = self._filtered_stmt(
            status=status, lead_time_class=lead_time_class,
            office_location=office_location, supplier_id=supplier_id,
            search=search, address_verification_status=address_verification_status,
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
    ) -> int:
        stmt = self._filtered_stmt(
            status=status, lead_time_class=lead_time_class,
            office_location=office_location, supplier_id=supplier_id,
            search=search, address_verification_status=address_verification_status,
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
    _SUPPLIER_VISIBLE_STATUSES = (
        "SENT_TO_SUPPLIER", "SUPPLIER_REVIEW", "CHANGE_REQUESTED", "CONFIRMED",
        "PREPARING", "OUT_FOR_DELIVERY", "DELIVERED", "COMPLETED", "UNABLE_TO_FULFIL",
    )

    def _supplier_scoped_stmt(self, *, supplier_id: int, search: str | None = None):
        stmt = select(BirthdayOrder).where(
            BirthdayOrder.supplier_id == supplier_id,
            BirthdayOrder.status.in_(self._SUPPLIER_VISIBLE_STATUSES),
        )
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                or_(BirthdayOrder.order_reference.ilike(like), BirthdayOrder.employee_name.ilike(like))
            )
        return stmt

    def list_for_supplier(
        self, *, supplier_id: int, search: str | None = None,
        sort_by: str | None = None, sort_direction: str = "desc",
        limit: int = 20, offset: int = 0,
    ) -> list[BirthdayOrder]:
        stmt = self._supplier_scoped_stmt(supplier_id=supplier_id, search=search)
        column = _SORTABLE_COLUMNS.get(sort_by or "", BirthdayOrder.delivery_date)
        stmt = stmt.order_by(column.desc() if sort_direction == "desc" else column.asc())
        stmt = stmt.limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())

    def count_for_supplier(self, *, supplier_id: int, search: str | None = None) -> int:
        stmt = self._supplier_scoped_stmt(supplier_id=supplier_id, search=search)
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

    def list_upcoming(self, *, days_ahead: int) -> list[BirthdayOrder]:
        today = date.today()
        cutoff = today + timedelta(days=days_ahead)
        stmt = (
            select(BirthdayOrder)
            .where(BirthdayOrder.birthday_date >= today, BirthdayOrder.birthday_date <= cutoff)
            .order_by(BirthdayOrder.birthday_date.asc())
        )
        return list(self.db.execute(stmt).scalars().all())
