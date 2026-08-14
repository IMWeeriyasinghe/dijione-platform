"""Get-or-create singleton BirthdayDetectionConfig row — reuses the same
get-or-create helper shape ``internal.py`` already has, exposed here as an
admin-manageable resource (plan §6, §9)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import BirthdayScope, require_birthday_permission
from app.db.session import get_db
from app.models.detection_config import BirthdayDetectionConfig
from app.schemas.config import DetectionConfigRead, DetectionConfigUpdate

router = APIRouter(prefix="/api/birthday/config", tags=["birthday-config"])


def get_or_create_config(db: Session) -> BirthdayDetectionConfig:
    config = db.query(BirthdayDetectionConfig).first()
    if config is None:
        config = BirthdayDetectionConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


@router.get("", response_model=DetectionConfigRead)
def get_config(
    db: Session = Depends(get_db),
    _scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> BirthdayDetectionConfig:
    return get_or_create_config(db)


@router.patch("", response_model=DetectionConfigRead)
def update_config(
    payload: DetectionConfigUpdate,
    db: Session = Depends(get_db),
    scope: BirthdayScope = Depends(require_birthday_permission("birthday.config.manage")),
) -> BirthdayDetectionConfig:
    config = get_or_create_config(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(config, field, value)
    config.updated_by = scope.user.id
    db.commit()
    db.refresh(config)
    return config
