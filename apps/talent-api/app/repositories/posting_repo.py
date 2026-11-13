from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import PostingClientMappingStatus
from app.models.client import Client
from app.models.posting_client_mapping import PostingClientMapping
from app.models.recruitment_posting_ref import RecruitmentPostingRef

_VERIFIED = PostingClientMappingStatus.VERIFIED.value
_UNMAPPED = PostingClientMappingStatus.UNMAPPED.value

# DTC resolution outcomes a TA must look at (mirrors the staff UI's list).
NEEDS_REVIEW_RESOLUTIONS = (
    "UNKNOWN_CLIENT_IDENTIFIER",
    "AMBIGUOUS_MULTIPLE_TAGS",
    "AMBIGUOUS_CLIENT_NAME",
    "MALFORMED_TAG",
    "CONFLICT_MANUAL_OVERRIDE",
)
POSTING_VIEWS = ("active", "verified", "unmapped", "review", "all")


def _view_condition(view: str):
    """SQL form of the Postings page filters. A posting with no mapping row
    is UNMAPPED (that is how it is presented), never VERIFIED or in review."""
    M, R = PostingClientMapping, RecruitmentPostingRef
    if view == "active":
        return R.state != "closed"
    if view == "verified":
        return M.status == _VERIFIED
    if view == "unmapped":
        return or_(M.id.is_(None), M.status == _UNMAPPED)
    if view == "review":
        return and_(M.status != _VERIFIED, M.resolution_status.in_(NEEDS_REVIEW_RESOLUTIONS))
    return None


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

    def list_page_for_staff(
        self,
        *,
        view: str,
        search: str | None = None,
        allowed_client_ids: list[int] | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[RecruitmentPostingRef, PostingClientMapping | None, str | None]], int, dict[str, int]]:
        """Staff Postings page: (posting, mapping, client name) rows, the
        total for ``view``, and per-view counts — all under the same scope and
        search. Portfolio staff see their clients' postings plus postings no
        client holds yet (same rule as the route's ``_can_view``), now in SQL
        so totals are exact. Client name comes from a join (no per-row
        lookup). Ordered ``last_seen_at DESC NULLS LAST, id DESC``."""
        M, R = PostingClientMapping, RecruitmentPostingRef
        join_on = (M.posting_external_id == R.external_id) & (M.provider == R.provider)
        base = []
        if allowed_client_ids is not None:
            base.append(
                or_(M.id.is_(None), M.client_id.is_(None), M.client_id.in_(allowed_client_ids))
            )
        if search and search.strip():
            like = f"%{search.strip()}%"
            base.append(or_(R.title.ilike(like), R.location.ilike(like)))

        counts_row = self.db.execute(
            select(
                *[
                    func.coalesce(func.sum(case((_view_condition(v), 1), else_=0)), 0).label(v)
                    if v != "all"
                    else func.count(R.id).label(v)
                    for v in POSTING_VIEWS
                ]
            )
            .select_from(R)
            .outerjoin(M, join_on)
            .where(*base)
        ).one()
        counts = {v: int(getattr(counts_row, v)) for v in POSTING_VIEWS}

        cond = _view_condition(view)
        where = base + ([cond] if cond is not None else [])
        stmt = (
            select(R, M, Client.name)
            .outerjoin(M, join_on)
            .outerjoin(Client, Client.id == M.client_id)
            .where(*where)
            .order_by(R.last_seen_at.desc().nullslast(), R.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = [(r[0], r[1], r[2]) for r in self.db.execute(stmt).all()]
        return rows, counts[view], counts

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
