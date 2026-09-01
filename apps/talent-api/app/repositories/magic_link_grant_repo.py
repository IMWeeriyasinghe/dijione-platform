from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.magic_link_grant import MagicLinkGrant


class MagicLinkGrantRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, grant_id: int) -> MagicLinkGrant | None:
        return self.db.get(MagicLinkGrant, grant_id)

    def get_by_token_hash(self, token_hash: str) -> MagicLinkGrant | None:
        return (
            self.db.execute(
                select(MagicLinkGrant).where(MagicLinkGrant.token_hash == token_hash)
            )
            .scalars()
            .first()
        )

    def get_by_public_id(self, public_id: str) -> MagicLinkGrant | None:
        return (
            self.db.execute(
                select(MagicLinkGrant).where(MagicLinkGrant.public_id == public_id)
            )
            .scalars()
            .first()
        )

    def list_for_scope(
        self,
        *,
        client_id: int | None = None,
        allowed_client_ids: list[int] | None = None,
    ) -> list[MagicLinkGrant]:
        """Grant history for the TA management screen, newest first.
        ``client_id`` filters to one client; ``allowed_client_ids`` is the
        portfolio restriction of a non-unrestricted staff member (``None``
        = ALL clients)."""
        stmt = select(MagicLinkGrant).order_by(MagicLinkGrant.issued_at.desc())
        if client_id is not None:
            stmt = stmt.where(MagicLinkGrant.client_id == client_id)
        elif allowed_client_ids is not None:
            stmt = stmt.where(MagicLinkGrant.client_id.in_(allowed_client_ids))
        return list(self.db.execute(stmt).scalars().all())
