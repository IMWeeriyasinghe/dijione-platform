"""Phase D supplier management schemas (plan §6)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SupplierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    primary_contact_name: str
    primary_contact_email: str
    primary_contact_phone: str
    escalation_contact_name: str
    escalation_contact_email: str
    lead_time_days: int
    working_days: str
    cutoff_time: str
    notes: str
    created_at: datetime
    updated_at: datetime


class SupplierCreate(BaseModel):
    name: str
    status: str = "ACTIVE"
    primary_contact_name: str = ""
    primary_contact_email: str = ""
    primary_contact_phone: str = ""
    escalation_contact_name: str = ""
    escalation_contact_email: str = ""
    lead_time_days: int = 0
    working_days: str = ""
    cutoff_time: str = ""
    notes: str = ""


class SupplierListResponse(BaseModel):
    items: list[SupplierRead]
    total: int
    page: int
    page_size: int


class SupplierUpdate(BaseModel):
    name: str | None = None
    status: str | None = None
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    primary_contact_phone: str | None = None
    escalation_contact_name: str | None = None
    escalation_contact_email: str | None = None
    lead_time_days: int | None = None
    working_days: str | None = None
    cutoff_time: str | None = None
    notes: str | None = None


class SupplierLocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    office_location: str
    is_primary: bool


class SupplierLocationCreate(BaseModel):
    office_location: str
    is_primary: bool = True


class SupplierCatalogueItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    name: str
    description: str
    is_active: bool


class SupplierCatalogueItemCreate(BaseModel):
    name: str
    description: str = ""
    is_active: bool = True


class SupplierCatalogueItemUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class SupplierUserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    supplier_id: int
    email: str
    full_name: str
    role: str
    status: str
    entra_object_id: str | None
    created_at: datetime
    updated_at: datetime


class SupplierUserCreate(BaseModel):
    email: str
    full_name: str = ""
    role: str = "SUPPLIER_USER"
    status: str = "ACTIVE"


class SupplierUserUpdate(BaseModel):
    """Email/name/role change over time as supplier contacts change;
    entra_object_id is deliberately NOT editable here — it is only ever
    set by the real Entra B2B guest-linking flow, never hand-entered."""

    email: str | None = None
    full_name: str | None = None
    role: str | None = None
    status: str | None = None
