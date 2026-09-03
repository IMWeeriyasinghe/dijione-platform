from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import PostingClientMappingStatus
from app.models.posting_client_mapping import PostingClientMapping
from app.models.recruitment_posting_ref import RecruitmentPostingRef

_VERIFIED = PostingClientMappingStatus.VERIFIED.value
_UNMAPPED = PostingClientMappingStatus.UNMAPPED.value


class PostingRepository:
    """All client-visibility access to postings goes through here so the
    fail-closed posting -> client rule is enforced in exactly one place.

    A client-scoped caller only ever reaches a posting via
    ``list_verified_for_client`` / ``get_verified_for_client``, which
    inner-join ``PostingClientMapping`` on ``(provider, posting_external_id)``
    filtered to ``status == VERIFIED AND client_id == <their own>``. Both
    sides are local tables (the posting projection + the trust record), so
    this decision never depends on recruitment-api being reachable.
    """

    def __init__(self, db: Session):
        self.db = db

    # --- staff (diagnostic) view -------------------------------------

    def get_ref_by_id(self, ref_id: int) -> RecruitmentPostingRef | None:
        return self.db.get(RecruitmentPostingRef, ref_id)

    def get_ref_by_external_id(self, external_id: str) -> RecruitmentPostingRef | None:
        return self.db.execute(
            select(RecruitmentPostingRef).where(RecruitmentPostingRef.external_id == external_id)
        ).scalars().first()

    def list_for_staff(
        self, *, unresolved_only: bool = False
    ) -> list[tuple[RecruitmentPostingRef, PostingClientMapping | None]]:
        stmt = select(RecruitmentPostingRef, PostingClientMapping).outerjoin(
            PostingClientMapping,
            (PostingClientMapping.posting_external_id == RecruitmentPostingRef.external_id)
            & (PostingClientMapping.provider == RecruitmentPostingRef.provider),
        )
        if unresolved_only:
            stmt = stmt.where(
                (PostingClientMapping.id.is_(None))
                | (PostingClientMapping.status == _UNMAPPED)
            )
        stmt = stmt.order_by(RecruitmentPostingRef.last_seen_at.desc().nullslast())
        return [(row[0], row[1]) for row in self.db.execute(stmt).all()]

    # --- client-scoped, fail-closed --------------------------------

    def list_verified_for_client(self, *, client_id: int) -> list[RecruitmentPostingRef]:
        stmt = (
            select(RecruitmentPostingRef)
            .join(
                PostingClientMapping,
                (PostingClientMapping.posting_external_id == RecruitmentPostingRef.external_id)
                & (PostingClientMapping.provider == RecruitmentPostingRef.provider),
            )
            .where(
                PostingClientMapping.status == _VERIFIED,
                PostingClientMapping.client_id == client_id,
            )
            .order_by(RecruitmentPostingRef.last_seen_at.desc().nullslast())
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_verified_for_client(
        self, ref_id: int, *, client_id: int
    ) -> RecruitmentPostingRef | None:
        stmt = (
            select(RecruitmentPostingRef)
            .join(
                PostingClientMapping,
                (PostingClientMapping.posting_external_id == RecruitmentPostingRef.external_id)
                & (PostingClientMapping.provider == RecruitmentPostingRef.provider),
            )
            .where(
                RecruitmentPostingRef.id == ref_id,
                PostingClientMapping.status == _VERIFIED,
                PostingClientMapping.client_id == client_id,
            )
        )
        return self.db.execute(stmt).scalars().first()

    # --- projection maintenance (from recruitment-api DTOs) --------

    def upsert_ref(self, dto: dict) -> RecruitmentPostingRef:
        from datetime import UTC, datetime

        ext = dto["external_id"]
        ref = self.get_ref_by_external_id(ext)
        dtc = dto.get("dtc_tag") or {}
        if ref is None:
            ref = RecruitmentPostingRef(provider=dto.get("provider", "LEVER"), external_id=ext)
            self.db.add(ref)
        ref.title = dto.get("title", "")
        ref.state = dto.get("state", "")
        ref.location = dto.get("location", "")
        ref.archived = bool(dto.get("archived", False))
        ref.dtc_status = dtc.get("status", "NO_TAG")
        ref.dtc_client_name = dtc.get("client_name")
        ref.dtc_raw_tag = dtc.get("raw_tag")
        ref.source_synced_at = _parse_iso(dto.get("synced_at"))
        ref.lever_created_at = _parse_iso(dto.get("lever_created_at"))
        ref.last_seen_at = datetime.now(UTC)
        self.db.flush()
        return ref


def _parse_iso(value):
    if not value:
        return None
    from datetime import datetime

    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
