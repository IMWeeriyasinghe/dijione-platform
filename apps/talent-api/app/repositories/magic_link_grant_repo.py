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

    def list_for_client(self, client_id: int) -> list[MagicLinkGrant]:
        return list(
            self.db.execute(
                select(MagicLinkGrant)
                .where(MagicLinkGrant.client_id == client_id)
                .order_by(MagicLinkGrant.issued_at.desc())
            )
            .scalars()
            .all()
        )
