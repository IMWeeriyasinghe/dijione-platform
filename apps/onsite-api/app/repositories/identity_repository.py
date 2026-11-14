"""Site-scoped access to the verified identity mapping tables.

Like every On-site repository, each public read REQUIRES ``allowed_site_ids``
(keyword-only, no default): mappings of a site the caller cannot see are
never returned.
"""

from __future__ import annotations

import json
from collections.abc import Collection
from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.identity import (
    MAPPING_VERIFIED,
    REJECTION_ACTIVE,
    IdentityEvent,
    IdentityMapping,
    IdentityRejection,
)


class IdentityRepository:
    def __init__(self, db: Session):
        self.db = db

    # --- reads -------------------------------------------------------------

    def verified_mappings(self, *, allowed_site_ids: Collection[str]) -> list[IdentityMapping]:
        if not allowed_site_ids:
            return []
        return list(self.db.execute(
            select(IdentityMapping)
            .where(IdentityMapping.site_id.in_(list(allowed_site_ids)), IdentityMapping.status == MAPPING_VERIFIED)
            .order_by(IdentityMapping.site_id, IdentityMapping.zk_emp_code, IdentityMapping.valid_from)
        ).scalars())

    def mappings(self, *, allowed_site_ids: Collection[str], site_id: str | None = None, zk_emp_code: str | None = None,
                 bamboohr_id: str | None = None, status: str | None = None) -> list[IdentityMapping]:
        if not allowed_site_ids or (site_id is not None and site_id not in allowed_site_ids):
            return []
        where = [IdentityMapping.site_id.in_([site_id] if site_id else list(allowed_site_ids))]
        if zk_emp_code is not None:
            where.append(IdentityMapping.zk_emp_code == zk_emp_code)
        if bamboohr_id is not None:
            where.append(IdentityMapping.bamboohr_id == bamboohr_id)
        if status is not None:
            where.append(IdentityMapping.status == status)
        return list(self.db.execute(
            select(IdentityMapping).where(*where)
            .order_by(IdentityMapping.site_id, IdentityMapping.zk_emp_code, IdentityMapping.valid_from,
                      IdentityMapping.id)
        ).scalars())

    def get_mapping(self, mapping_id: int, *, allowed_site_ids: Collection[str]) -> IdentityMapping | None:
        m = self.db.get(IdentityMapping, mapping_id)
        return m if m is not None and m.site_id in allowed_site_ids else None

    def overlapping_verified(self, *, allowed_site_ids: Collection[str], site_id: str, zk_emp_code: str,
                             start: date, end: date | None, exclude_ids: Collection[int] = ()) -> list[IdentityMapping]:
        """VERIFIED periods of this code intersecting ``[start, end or ∞]`` (inclusive)."""
        if site_id not in allowed_site_ids:
            return []
        where = [IdentityMapping.site_id == site_id, IdentityMapping.zk_emp_code == zk_emp_code,
                 IdentityMapping.status == MAPPING_VERIFIED,
                 (IdentityMapping.valid_to.is_(None)) | (IdentityMapping.valid_to >= start)]
        if end is not None:
            where.append(IdentityMapping.valid_from <= end)
        if exclude_ids:
            where.append(IdentityMapping.id.notin_(list(exclude_ids)))
        return list(self.db.execute(select(IdentityMapping).where(*where)).scalars())

    def rejections(self, *, allowed_site_ids: Collection[str], site_id: str | None = None,
                   zk_emp_code: str | None = None, active_only: bool = True) -> list[IdentityRejection]:
        if not allowed_site_ids or (site_id is not None and site_id not in allowed_site_ids):
            return []
        where = [IdentityRejection.site_id.in_([site_id] if site_id else list(allowed_site_ids))]
        if zk_emp_code is not None:
            where.append(IdentityRejection.zk_emp_code == zk_emp_code)
        if active_only:
            where.append(IdentityRejection.status == REJECTION_ACTIVE)
        return list(self.db.execute(select(IdentityRejection).where(*where).order_by(IdentityRejection.id)).scalars())

    def get_rejection(self, rejection_id: int, *, allowed_site_ids: Collection[str]) -> IdentityRejection | None:
        r = self.db.get(IdentityRejection, rejection_id)
        return r if r is not None and r.site_id in allowed_site_ids else None

    def events(self, *, entity_type: str | None = None, entity_ids: Collection[int] | None = None,
               limit: int = 200) -> list[IdentityEvent]:
        where = []
        if entity_type is not None:
            where.append(IdentityEvent.entity_type == entity_type)
        if entity_ids is not None:
            where.append(IdentityEvent.entity_id.in_(list(entity_ids) or [-1]))
        return list(self.db.execute(
            select(IdentityEvent).where(*where).order_by(IdentityEvent.at.desc(), IdentityEvent.id.desc()).limit(limit)
        ).scalars())

    def count_mappings_without_evidence(self, *, allowed_site_ids: Collection[str]) -> int:
        if not allowed_site_ids:
            return 0
        return int(self.db.execute(
            select(func.count()).select_from(IdentityMapping).where(
                IdentityMapping.site_id.in_(list(allowed_site_ids)), IdentityMapping.status == MAPPING_VERIFIED,
                func.length(func.trim(IdentityMapping.evidence)) < 10)
        ).scalar_one())

    # --- writes (caller owns the transaction) ------------------------------

    def lock_code(self, site_id: str, zk_emp_code: str) -> None:
        """Serialise writers per (site, code) for the rest of the transaction.
        Postgres: transaction-scoped advisory lock. SQLite serialises writers
        at the database level, so nothing is needed there."""
        if self.db.get_bind().dialect.name == "postgresql":
            self.db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                            {"k": f"onsite-identity:{site_id}:{zk_emp_code}"})

    def add_event(self, *, entity_type: str, entity_id: int, action: str, actor_user_id: int,
                  previous: dict | None = None, new: dict | None = None, note: str | None = None) -> IdentityEvent:
        ev = IdentityEvent(entity_type=entity_type, entity_id=entity_id, action=action, actor_user_id=actor_user_id,
                           previous_json=json.dumps(previous, default=str, sort_keys=True) if previous else None,
                           new_json=json.dumps(new, default=str, sort_keys=True) if new else None, note=note)
        self.db.add(ev)
        return ev
