"""Get-or-create singleton BirthdayDetectionConfig row — reuses the same
get-or-create helper shape ``internal.py`` already has, exposed here as an
admin-manageable resource (plan §6, §9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import BirthdayScope, require_birthday_permission
from app.db.session import get_db
from app.models.detection_config import BirthdayDetectionConfig
from app.schemas.config import CleanStartApply, CleanStartPreview, DetectionConfigRead, DetectionConfigUpdate
from app.services import operational_start_service

router = APIRouter(prefix="/api/birthday/config", tags=["birthday-config"])


def get_or_create_config(db: Session) -> BirthdayDetectionConfig:
    config = db.query(BirthdayDetectionConfig).first()
    if config is None:
        config = BirthdayDetectionConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _read(config: BirthdayDetectionConfig) -> DetectionConfigRead:
    read = DetectionConfigRead.model_validate(config)
    read.first_eligible_birthday = operational_start_service.first_eligible_birthday(config)
    return read


@router.get("", response_model=DetectionConfigRead)
def get_config(
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> DetectionConfigRead:
    return _read(get_or_create_config(db))


@router.patch("", response_model=DetectionConfigRead)
def update_config(
    payload: DetectionConfigUpdate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> DetectionConfigRead:
    # Saving settings never cancels orders: the pre-launch backlog is only
    # cleared by the explicit, single-use clean start below.
    config = get_or_create_config(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "supplier_lead_time_days" and value is None:
            continue
        setattr(config, field, value)
    config.updated_by = scope.user.id
    db.commit()
    db.refresh(config)
    return _read(config)


@router.get("/clean-start/preview", response_model=CleanStartPreview)
def preview_clean_start(
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> CleanStartPreview:
    return CleanStartPreview(**operational_start_service.preview_clean_start(db, get_or_create_config(db)))


@router.post("/clean-start", response_model=CleanStartPreview)
def apply_clean_start(
    payload: CleanStartApply,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> CleanStartPreview:
    if not payload.confirm:
        raise HTTPException(422, "The clean start must be explicitly confirmed")
    config = get_or_create_config(db)
    try:
        operational_start_service.apply_clean_start(
            db, config, confirmed_first_eligible=payload.first_eligible_birthday,
            actor_id=scope.user.id, actor_display_name=getattr(scope.user, "full_name", None),
        )
    except operational_start_service.CleanStartError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    db.refresh(config)
    return CleanStartPreview(**operational_start_service.preview_clean_start(db, config))
