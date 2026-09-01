from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import PostingClientMappingStatus
from app.models.posting_client_mapping import PostingClientMapping

_LEVER = "LEVER"


class PostingClientMappingRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_for_posting(
        self, posting_external_id: str, *, provider: str = _LEVER
    ) -> PostingClientMapping | None:
        return self.db.execute(
            select(PostingClientMapping).where(
                PostingClientMapping.provider == provider,
                PostingClientMapping.posting_external_id == posting_external_id,
            )
        ).scalars().first()

    def get_or_create(
        self, posting_external_id: str, *, provider: str = _LEVER
    ) -> PostingClientMapping:
        existing = self.get_for_posting(posting_external_id, provider=provider)
        if existing is not None:
            return existing
        mapping = PostingClientMapping(
            provider=provider, posting_external_id=posting_external_id
        )
        self.db.add(mapping)
        self.db.flush()
        return mapping

    def list_all(self) -> list[PostingClientMapping]:
        return list(self.db.execute(select(PostingClientMapping)).scalars().all())

    def list_verified(self) -> list[PostingClientMapping]:
        """VERIFIED postings eligible for promotion into a TalentRequest.
        ``client_id IS NOT NULL`` is a defence-in-depth belt: a VERIFIED row
        whose Client was since deleted (client_id -> SET NULL) must never
        promote — fail closed, same as every other client-visibility path."""
        return list(
            self.db.execute(
                select(PostingClientMapping).where(
                    PostingClientMapping.status == PostingClientMappingStatus.VERIFIED.value,
                    PostingClientMapping.client_id.is_not(None),
                )
            ).scalars().all()
        )

    def by_source(self, source: str) -> list[PostingClientMapping]:
        return list(
            self.db.execute(
                select(PostingClientMapping).where(PostingClientMapping.source == source)
            ).scalars().all()
        )

    def add(self, mapping: PostingClientMapping) -> PostingClientMapping:
        self.db.add(mapping)
        self.db.flush()
        return mapping
