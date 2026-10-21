from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mirror import SiteSettings, SourceSite


class SiteRepository:
    """Site discovery + DijiOne-owned settings. Admin listing deliberately
    includes disabled sites (that is how an admin enables one); data reads
    elsewhere only ever see ``enabled_site_ids()``."""

    def __init__(self, db: Session):
        self.db = db

    def enabled_site_ids(self) -> list[str]:
        return list(self.db.execute(
            select(SiteSettings.site_id).where(SiteSettings.enabled.is_(True)).order_by(SiteSettings.site_id)
        ).scalars())

    def all_sites(self) -> list[tuple[SourceSite | None, SiteSettings]]:
        settings = list(self.db.execute(select(SiteSettings).order_by(SiteSettings.site_id)).scalars())
        sources = {s.site_id: s for s in self.db.execute(select(SourceSite)).scalars()}
        return [(sources.get(s.site_id), s) for s in settings]

    def get(self, site_id: str) -> tuple[SourceSite | None, SiteSettings] | None:
        settings = self.db.execute(select(SiteSettings).where(SiteSettings.site_id == site_id)).scalars().first()
        if settings is None:
            return None
        return self.db.get(SourceSite, site_id), settings

    def time_zones(self, site_ids) -> dict[str, str]:
        return {
            s.site_id: s.time_zone
            for s in self.db.execute(select(SourceSite).where(SourceSite.site_id.in_(list(site_ids)))).scalars()
        }
