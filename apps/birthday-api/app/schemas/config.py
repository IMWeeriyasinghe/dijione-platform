from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Year-independent sanity window for the operational start date: within a
# year either side of today (works in any year without code changes).
OPERATIONAL_START_WINDOW_DAYS = 365
MAX_SUPPLIER_LEAD_TIME_DAYS = 60


class DetectionConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    normal_threshold_days: int
    short_notice_threshold_days: int
    urgent_threshold_days: int
    window_lookback_days: int
    window_lookahead_days: int
    default_quantity: int
    verify_buffer_days: int
    acknowledgement_sla_hours: int
    auto_release_enabled: bool
    operational_start_date: date | None = None
    supplier_lead_time_days: int = 7
    first_eligible_birthday: date | None = None
    clean_start_applied_at: datetime | None = None
    clean_start_applied_by: int | None = None
    clean_start_excluded_count: int | None = None
    clean_start_first_eligible: date | None = None
    updated_by: int | None


class DetectionConfigUpdate(BaseModel):
    normal_threshold_days: int | None = None
    short_notice_threshold_days: int | None = None
    urgent_threshold_days: int | None = None
    window_lookback_days: int | None = None
    window_lookahead_days: int | None = None
    default_quantity: int | None = None
    verify_buffer_days: int | None = None
    acknowledgement_sla_hours: int | None = None
    auto_release_enabled: bool | None = None
    operational_start_date: date | None = None
    supplier_lead_time_days: int | None = Field(default=None, ge=0, le=MAX_SUPPLIER_LEAD_TIME_DAYS)

    @field_validator("operational_start_date")
    @classmethod
    def _start_date_in_window(cls, value: date | None) -> date | None:
        if value is None:
            return value
        today = datetime.now(UTC).date()
        window = timedelta(days=OPERATIONAL_START_WINDOW_DAYS)
        if not (today - window <= value <= today + window):
            raise ValueError(
                f"Operational start date must be within {OPERATIONAL_START_WINDOW_DAYS} days of today"
            )
        return value


class CleanStartPreview(BaseModel):
    operational_start_date: date | None
    supplier_lead_time_days: int
    first_eligible_birthday: date | None
    total: int
    by_status: dict[str, int]
    released_to_supplier: int
    already_applied: bool
    clean_start_applied_at: datetime | None = None
    clean_start_excluded_count: int | None = None


class CleanStartApply(BaseModel):
    """The admin must echo the boundary they previewed, so a settings
    change between preview and confirm cannot apply a different cut-off."""

    confirm: bool
    first_eligible_birthday: date
