"""Phase D supplier management — BirthdayScope-gated per plan §6. All
mutating actions call ``audit_service.log(...)`` per existing convention."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import BirthdayScope, require_birthday_permission
from app.db.session import get_db
from app.models.supplier import Supplier
from app.models.supplier_catalogue_item import SupplierCatalogueItem
from app.models.supplier_location import SupplierLocation
from app.models.supplier_user import SupplierUser
from app.repositories.supplier_repository import SupplierRepository
from app.schemas.supplier import (
    SupplierCatalogueItemCreate,
    SupplierCatalogueItemRead,
    SupplierCatalogueItemUpdate,
    SupplierCreate,
    SupplierListResponse,
    SupplierLocationCreate,
    SupplierLocationRead,
    SupplierRead,
    SupplierUpdate,
    SupplierUserCreate,
    SupplierUserRead,
    SupplierUserUpdate,
)
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/birthday/suppliers", tags=["birthday-suppliers"])


def _get_supplier_or_404(db: Session, supplier_id: int) -> Supplier:
    supplier = SupplierRepository(db).get_by_id(supplier_id)
    if supplier is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier not found")
    return supplier


def _audit(scope: BirthdayScope, action: str, entity_id: int, **kwargs) -> None:
    try:
        AuditService().log(
            actor_id=scope.user.id, action=action, entity_type="supplier", entity_id=entity_id, **kwargs,
        )
    except Exception:  # noqa: BLE001 - best-effort
        pass


@router.get("", response_model=SupplierListResponse)
def list_suppliers(
    search: str | None = None,
    status_filter: str | None = None,
    sort_by: str | None = None,
    sort_direction: str = "asc",
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.suppliers.read")),
) -> SupplierListResponse:
    if sort_direction not in ("asc", "desc"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "sort_direction must be 'asc' or 'desc'")
    page = max(page, 1)
    page_size = max(1, min(page_size, 200))
    repo = SupplierRepository(db)
    items = repo.list_filtered(
        search=search, status=status_filter, sort_by=sort_by, sort_direction=sort_direction,
        limit=page_size, offset=(page - 1) * page_size,
    )
    total = repo.count_filtered(search=search, status=status_filter)
    return SupplierListResponse(items=items, total=total, page=page, page_size=page_size)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SupplierRead)
def create_supplier(
    payload: SupplierCreate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.suppliers.manage")),
) -> Supplier:
    repo = SupplierRepository(db)
    supplier = repo.create(Supplier(**payload.model_dump()))
    db.flush()
    if supplier.is_default:
        repo.clear_default_except(supplier.id)
    db.commit()
    db.refresh(supplier)
    _audit(scope, "birthday.supplier.create", supplier.id, new_state={"name": supplier.name})
    return supplier


@router.get("/{supplier_id}", response_model=SupplierRead)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.suppliers.read")),
) -> Supplier:
    return _get_supplier_or_404(db, supplier_id)


@router.patch("/{supplier_id}", response_model=SupplierRead)
def update_supplier(
    supplier_id: int,
    payload: SupplierUpdate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.suppliers.manage")),
) -> Supplier:
    supplier = _get_supplier_or_404(db, supplier_id)
    updates = payload.model_dump(exclude_unset=True)
    repo = SupplierRepository(db)
    repo.update(supplier, updates)
    db.flush()
    if updates.get("is_default"):
        # Setting this supplier as the island-wide default clears the flag
        # on every other supplier — at most one default at a time.
        repo.clear_default_except(supplier.id)
    db.commit()
    db.refresh(supplier)
    _audit(scope, "birthday.supplier.update", supplier.id, new_state=updates)
    return supplier


@router.get("/{supplier_id}/locations", response_model=list[SupplierLocationRead])
def list_locations(
    supplier_id: int,
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.suppliers.read")),
) -> list[SupplierLocation]:
    _get_supplier_or_404(db, supplier_id)
    return SupplierRepository(db).list_locations(supplier_id)


@router.post(
    "/{supplier_id}/locations", status_code=status.HTTP_201_CREATED, response_model=SupplierLocationRead
)
def add_location(
    supplier_id: int,
    payload: SupplierLocationCreate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.suppliers.manage")),
) -> SupplierLocation:
    _get_supplier_or_404(db, supplier_id)
    location = SupplierRepository(db).add_location(
        SupplierLocation(supplier_id=supplier_id, **payload.model_dump())
    )
    db.commit()
    db.refresh(location)
    _audit(
        scope, "birthday.supplier.location_add", supplier_id,
        new_state={"office_location": location.office_location},
    )
    return location


@router.get("/{supplier_id}/catalogue", response_model=list[SupplierCatalogueItemRead])
def list_catalogue(
    supplier_id: int,
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.suppliers.read")),
) -> list[SupplierCatalogueItem]:
    _get_supplier_or_404(db, supplier_id)
    return SupplierRepository(db).list_catalogue_items(supplier_id)


@router.post(
    "/{supplier_id}/catalogue", status_code=status.HTTP_201_CREATED, response_model=SupplierCatalogueItemRead
)
def add_catalogue_item(
    supplier_id: int,
    payload: SupplierCatalogueItemCreate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.suppliers.manage")),
) -> SupplierCatalogueItem:
    _get_supplier_or_404(db, supplier_id)
    repo = SupplierRepository(db)
    if payload.is_default:
        _clear_default_catalogue_item(repo, supplier_id)
    item = repo.add_catalogue_item(
        SupplierCatalogueItem(supplier_id=supplier_id, **payload.model_dump())
    )
    db.commit()
    db.refresh(item)
    _audit(scope, "birthday.supplier.catalogue_add", supplier_id, new_state={"name": item.name})
    return item


@router.patch("/{supplier_id}/catalogue/{item_id}", response_model=SupplierCatalogueItemRead)
def update_catalogue_item(
    supplier_id: int,
    item_id: int,
    payload: SupplierCatalogueItemUpdate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.suppliers.manage")),
) -> SupplierCatalogueItem:
    _get_supplier_or_404(db, supplier_id)
    repo = SupplierRepository(db)
    item = repo.get_catalogue_item(supplier_id, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catalogue item not found")
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("is_default") is True:
        _clear_default_catalogue_item(repo, supplier_id, except_item_id=item.id)
    repo.update_catalogue_item(item, updates)
    db.commit()
    db.refresh(item)
    _audit(scope, "birthday.supplier.catalogue_update", supplier_id, new_state=updates)
    return item


def _clear_default_catalogue_item(repo: SupplierRepository, supplier_id: int, *, except_item_id: int | None = None) -> None:
    """At most one default cake per supplier (plan §31/§L) — mirrors the
    is_default-at-most-one pattern already used for suppliers themselves."""
    for existing in repo.list_catalogue_items(supplier_id):
        if existing.is_default and existing.id != except_item_id:
            existing.is_default = False


# -- Supplier Users ------------------------------------------------------
# Admin-only (birthday.suppliers.manage) CRUD for the accounts that will
# authenticate into the supplier portal. Never hard-deleted (plan
# requirement) — deactivation is the only destructive-looking action, and
# it's a status flip, not a row removal, so historical OrderEvent/audit
# actor references stay resolvable.

_VALID_ROLES = {"SUPPLIER_USER", "SUPPLIER_ADMIN"}
_VALID_USER_STATUSES = {"ACTIVE", "INACTIVE"}


@router.get("/{supplier_id}/users", response_model=list[SupplierUserRead])
def list_supplier_users(
    supplier_id: int,
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.suppliers.read")),
) -> list[SupplierUser]:
    _get_supplier_or_404(db, supplier_id)
    return SupplierRepository(db).list_users(supplier_id)


@router.post(
    "/{supplier_id}/users", status_code=status.HTTP_201_CREATED, response_model=SupplierUserRead
)
def create_supplier_user(
    supplier_id: int,
    payload: SupplierUserCreate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.suppliers.manage")),
) -> SupplierUser:
    _get_supplier_or_404(db, supplier_id)
    if payload.role not in _VALID_ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid role: {payload.role!r}")
    if payload.status not in _VALID_USER_STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid status: {payload.status!r}")

    existing = db.execute(select(SupplierUser).where(SupplierUser.email == payload.email)).scalars().first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"A supplier user with email {payload.email!r} already exists")

    user = SupplierRepository(db).add_user(
        SupplierUser(
            supplier_id=supplier_id, email=payload.email, full_name=payload.full_name,
            role=payload.role, status=payload.status,
        )
    )
    db.commit()
    db.refresh(user)
    _audit(scope, "birthday.supplier.user_create", supplier_id, new_state={"email": user.email})
    return user


@router.patch("/{supplier_id}/users/{user_id}", response_model=SupplierUserRead)
def update_supplier_user(
    supplier_id: int,
    user_id: int,
    payload: SupplierUserUpdate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.suppliers.manage")),
) -> SupplierUser:
    """Covers edit (email/name/role) and activate/deactivate (status) —
    one endpoint, since both are just a partial update of the same row."""
    _get_supplier_or_404(db, supplier_id)
    repo = SupplierRepository(db)
    user = repo.get_user(supplier_id, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier user not found")

    updates = payload.model_dump(exclude_unset=True)
    if "role" in updates and updates["role"] not in _VALID_ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid role: {updates['role']!r}")
    if "status" in updates and updates["status"] not in _VALID_USER_STATUSES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Invalid status: {updates['status']!r}")
    if "email" in updates and updates["email"] != user.email:
        existing = db.execute(
            select(SupplierUser).where(SupplierUser.email == updates["email"])
        ).scalars().first()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"A supplier user with email {updates['email']!r} already exists")
    if "entra_object_id" in updates:
        # Normalise "" -> None so the unique index never sees empty strings.
        updates["entra_object_id"] = (updates["entra_object_id"] or "").strip() or None
    entra_link_changed = (
        "entra_object_id" in updates and updates["entra_object_id"] != user.entra_object_id
    )
    if entra_link_changed and updates["entra_object_id"]:
        clash = db.execute(
            select(SupplierUser).where(SupplierUser.entra_object_id == updates["entra_object_id"])
        ).scalars().first()
        if clash is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "That Entra object id is already linked to another supplier user",
            )

    repo.update_user(user, updates)
    db.commit()
    db.refresh(user)
    # Audit the identity link separately from routine profile edits — it is
    # the security-relevant action (§23/§39: "Entra identity linked").
    if entra_link_changed:
        _audit(
            scope, "birthday.supplier.user_entra_linked", supplier_id,
            new_state={"supplier_user_id": user.id, "linked": bool(user.entra_object_id)},
        )
    _audit(scope, "birthday.supplier.user_update", supplier_id, new_state=updates)
    return user
