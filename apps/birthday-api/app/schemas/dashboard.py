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
    # Phase 1.6 §6 (R6) — split from the old, misleadingly-named single
    # supplier_not_accepted_count (which was secretly SLA-gated).
    acceptance_awaiting_count: int
    acceptance_overdue_count: int
    deliveries_today_at_risk_count: int
    # Phase 1 §1.2 — attention + detection health.
    on_hold_count: int = 0
    overdue_delivery_count: int = 0
    open_issues_count: int = 0
    unmatched_emails_count: int = 0
    detection_health: dict = {}


class UpcomingOrdersResponse(BaseModel):
    days_ahead: int
    orders: list[BirthdayOrderSummary]
