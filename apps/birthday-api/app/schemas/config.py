from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class DetectionConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    normal_threshold_days: int
    short_notice_threshold_days: int
    urgent_threshold_days: int
    window_lookback_days: int
    window_lookahead_days: int
    updated_by: int | None


class DetectionConfigUpdate(BaseModel):
    normal_threshold_days: int | None = None
    short_notice_threshold_days: int | None = None
    urgent_threshold_days: int | None = None
    window_lookback_days: int | None = None
    window_lookahead_days: int | None = None
