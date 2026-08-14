from __future__ import annotations

from pydantic import BaseModel

from app.schemas.order import BirthdayOrderSummary


class DashboardSummary(BaseModel):
    total_orders: int
    by_status: dict[str, int]
    by_lead_time_class: dict[str, int]
    upcoming_count: int
    exceptions_count: int


class UpcomingOrdersResponse(BaseModel):
    days_ahead: int
    orders: list[BirthdayOrderSummary]
