from __future__ import annotations

from pydantic import BaseModel

from app.schemas.order import BirthdayOrderSummary


class DashboardSummary(BaseModel):
    total_orders: int
    by_status: dict[str, int]
    by_lead_time_class: dict[str, int]
    upcoming_count: int
    exceptions_count: int
    # Actionable attention cards (plan §M) — each maps to a filtered
    # queue in the UI, not a static vanity count.
    pending_verification_count: int
    verification_overdue_count: int
    requires_review_count: int
    supplier_not_accepted_count: int
    deliveries_today_at_risk_count: int


class UpcomingOrdersResponse(BaseModel):
    days_ahead: int
    orders: list[BirthdayOrderSummary]
