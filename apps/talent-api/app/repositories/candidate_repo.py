from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.candidate import Candidate
from app.models.talent_request import TalentRequest


class CandidateRepository:
    """Candidate pool is global (master record, CLAUDE.md §19) — not
    tenant-scoped for an unrestricted staff caller. Client-facing visibility
    is enforced separately via Application.is_client_visible, never by
    filtering this repository. A portfolio-restricted staff caller
    (``allowed_client_ids`` not None) is the one exception: ``list_all``
    narrows to candidates with at least one application against an
    in-portfolio client, so a restricted TA's Candidate Pool list doesn't
    surface a candidate whose only applications belong to other clients."""

    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, candidate_id: int) -> Candidate | None:
        return self.db.get(Candidate, candidate_id)

    def get_by_email(self, email: str) -> Candidate | None:
        stmt = select(Candidate).where(Candidate.email == email)
        return self.db.execute(stmt).scalars().first()

    def get_by_lever_external_id(self, lever_external_id: str) -> Candidate | None:
        stmt = select(Candidate).where(Candidate.lever_external_id == lever_external_id)
        return self.db.execute(stmt).scalars().first()

    def map_by_lever_external_ids(self, lever_external_ids, *, chunk: int = 1000) -> dict[str, Candidate]:
        """One query per ``chunk`` ids instead of one per candidate."""
        ids = sorted(set(lever_external_ids))
        found: dict[str, Candidate] = {}
        for start in range(0, len(ids), chunk):
            stmt = select(Candidate).where(Candidate.lever_external_id.in_(ids[start:start + chunk]))
            found.update((c.lever_external_id, c) for c in self.db.execute(stmt).scalars())
        return found

    def list_all(
        self, search: str | None = None, *, allowed_client_ids: list[int] | None = None
    ) -> list[Candidate]:
        stmt = select(Candidate)
        if allowed_client_ids is not None:
            stmt = (
                stmt.join(Application, Application.candidate_id == Candidate.id)
                .join(TalentRequest, TalentRequest.id == Application.talent_request_id)
                .where(TalentRequest.client_id.in_(allowed_client_ids))
                .distinct()
            )
        if search:
            like = f"%{search}%"
            stmt = stmt.where(
                (Candidate.full_name.ilike(like)) | (Candidate.professional_title.ilike(like))
            )
        stmt = stmt.order_by(Candidate.full_name)
        return list(self.db.execute(stmt).scalars().all())

    def list_page(
        self,
        *,
        search: str | None = None,
        allowed_client_ids: list[int] | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Candidate], int]:
        """Database-level page of the Candidate Pool plus the total match
        count. Same scoping/search semantics as ``list_all``. Ordering is
        ``(full_name, id)`` so pages are stable even when names repeat.
        Portfolio scoping uses an ``id IN (subquery)`` filter rather than
        JOIN + DISTINCT so LIMIT/OFFSET and COUNT apply to unique
        candidates."""
        conds = []
        if allowed_client_ids is not None:
            scoped_ids = (
                select(Application.candidate_id)
                .join(TalentRequest, TalentRequest.id == Application.talent_request_id)
                .where(TalentRequest.client_id.in_(allowed_client_ids))
            )
            conds.append(Candidate.id.in_(scoped_ids))
        if search and search.strip():
            like = f"%{search.strip()}%"
            conds.append(
                (Candidate.full_name.ilike(like)) | (Candidate.professional_title.ilike(like))
            )
        total = self.db.execute(
            select(func.count()).select_from(Candidate).where(*conds)
        ).scalar_one()
        rows = (
            self.db.execute(
                select(Candidate)
                .where(*conds)
                .order_by(Candidate.full_name, Candidate.id)
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )
        return list(rows), int(total)

    def add(self, candidate: Candidate) -> Candidate:
        self.db.add(candidate)
        self.db.flush()
        return candidate
