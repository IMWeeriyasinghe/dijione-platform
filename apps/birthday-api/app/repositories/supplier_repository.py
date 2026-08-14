from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.supplier import Supplier
from app.models.supplier_catalogue_item import SupplierCatalogueItem
from app.models.supplier_location import SupplierLocation
from app.models.supplier_user import SupplierUser

_SUPPLIER_SORTABLE_COLUMNS = {
    "name": Supplier.name,
    "status": Supplier.status,
    "lead_time_days": Supplier.lead_time_days,
    "created_at": Supplier.created_at,
}


class SupplierRepository:
    """Full CRUD for Phase D supplier management, plus the
    ``get_by_office_location`` lookup detection_service depends on
    (signature preserved unchanged)."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, supplier_id: int) -> Supplier | None:
        return self.db.get(Supplier, supplier_id)

    def list(self) -> list[Supplier]:
        stmt = select(Supplier).order_by(Supplier.name)
        return list(self.db.execute(stmt).scalars().all())

    @staticmethod
    def _filtered_stmt(*, search: str | None = None, status: str | None = None):
        stmt = select(Supplier)
        if status is not None:
            stmt = stmt.where(Supplier.status == status)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(Supplier.name.ilike(like), Supplier.primary_contact_email.ilike(like)))
        return stmt

    def list_filtered(
        self, *, search: str | None = None, status: str | None = None,
        sort_by: str | None = None, sort_direction: str = "asc",
        limit: int = 20, offset: int = 0,
    ) -> list[Supplier]:
        stmt = self._filtered_stmt(search=search, status=status)
        column = _SUPPLIER_SORTABLE_COLUMNS.get(sort_by or "", Supplier.name)
        stmt = stmt.order_by(column.desc() if sort_direction == "desc" else column.asc())
        stmt = stmt.limit(limit).offset(offset)
        return list(self.db.execute(stmt).scalars().all())

    def count_filtered(self, *, search: str | None = None, status: str | None = None) -> int:
        stmt = self._filtered_stmt(search=search, status=status)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        return self.db.execute(count_stmt).scalar_one()

    def create(self, supplier: Supplier) -> Supplier:
        self.db.add(supplier)
        self.db.flush()
        return supplier

    def update(self, supplier: Supplier, updates: dict) -> Supplier:
        for field, value in updates.items():
            setattr(supplier, field, value)
        self.db.flush()
        return supplier

    def get_by_office_location(self, office_location: str) -> Supplier | None:
        """Only ever resolves an ACTIVE supplier — an INACTIVE supplier
        must not be auto-assigned to newly detected orders (plan
        requirement)."""
        stmt = (
            select(Supplier)
            .join(SupplierLocation, SupplierLocation.supplier_id == Supplier.id)
            .where(SupplierLocation.office_location == office_location, Supplier.status == "ACTIVE")
        )
        return self.db.execute(stmt).scalars().first()

    # -- Locations ---------------------------------------------------

    def add_location(self, location: SupplierLocation) -> SupplierLocation:
        self.db.add(location)
        self.db.flush()
        return location

    def list_locations(self, supplier_id: int) -> list[SupplierLocation]:
        stmt = (
            select(SupplierLocation)
            .where(SupplierLocation.supplier_id == supplier_id)
            .order_by(SupplierLocation.id)
        )
        return list(self.db.execute(stmt).scalars().all())

    # -- Catalogue -----------------------------------------------------

    def add_catalogue_item(self, item: SupplierCatalogueItem) -> SupplierCatalogueItem:
        self.db.add(item)
        self.db.flush()
        return item

    def list_catalogue_items(self, supplier_id: int) -> list[SupplierCatalogueItem]:
        stmt = (
            select(SupplierCatalogueItem)
            .where(SupplierCatalogueItem.supplier_id == supplier_id)
            .order_by(SupplierCatalogueItem.id)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_catalogue_item(self, supplier_id: int, item_id: int) -> SupplierCatalogueItem | None:
        item = self.db.get(SupplierCatalogueItem, item_id)
        if item is None or item.supplier_id != supplier_id:
            return None
        return item

    def update_catalogue_item(self, item: SupplierCatalogueItem, updates: dict) -> SupplierCatalogueItem:
        for field, value in updates.items():
            setattr(item, field, value)
        self.db.flush()
        return item

    # -- Supplier Users -------------------------------------------------

    def list_users(self, supplier_id: int) -> list[SupplierUser]:
        stmt = select(SupplierUser).where(SupplierUser.supplier_id == supplier_id).order_by(SupplierUser.id)
        return list(self.db.execute(stmt).scalars().all())

    def get_user(self, supplier_id: int, user_id: int) -> SupplierUser | None:
        user = self.db.get(SupplierUser, user_id)
        if user is None or user.supplier_id != supplier_id:
            return None
        return user

    def add_user(self, user: SupplierUser) -> SupplierUser:
        self.db.add(user)
        self.db.flush()
        return user

    def update_user(self, user: SupplierUser, updates: dict) -> SupplierUser:
        for field, value in updates.items():
            setattr(user, field, value)
        self.db.flush()
        return user
