from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.application import Application
from app.models.talent_request import TalentRequest
from app.repositories.talent_request_repo import client_may_access_request


class ApplicationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(
        self,
        application_id: int,
        *,
        client_id: int | None = None,
        allowed_client_ids: list[int] | None = None,
    ) -> Application | None:
        stmt = (
            select(Application)
            .options(joinedload(Application.candidate), joinedload(Application.talent_request))
            .where(Application.id == application_id)
        )
        if client_id is not None:
            stmt = stmt.join(TalentRequest).where(
                TalentRequest.client_id == client_id, client_may_access_request()
            )
        elif allowed_client_ids is not None:
            stmt = stmt.join(TalentRequest).where(TalentRequest.client_id.in_(allowed_client_ids))
        return self.db.execute(stmt).scalars().first()

    def list_for_request(
        self, request_id: int, *, client_visible_only: bool = False
    ) -> list[Application]:
        stmt = (
            select(Application)
            .options(joinedload(Application.candidate))
            .where(Application.talent_request_id == request_id)
        )
        if client_visible_only:
            stmt = stmt.where(Application.is_client_visible.is_(True))
        return list(self.db.execute(stmt).scalars().all())

    def list_for_candidate(
        self, candidate_id: int, *, allowed_client_ids: list[int] | None = None
    ) -> list[Application]:
        """``allowed_client_ids`` restricts the result to applications whose
        request belongs to a portfolio-scoped staff member's assigned
        clients. ``None`` (unrestricted staff — the Candidate Ownership Rule,
        CLAUDE.md §19) returns every application across every client."""
        stmt = (
            select(Application)
            .options(joinedload(Application.talent_request).joinedload(TalentRequest.client))
            .where(Application.candidate_id == candidate_id)
        )
        if allowed_client_ids is not None:
            stmt = stmt.join(TalentRequest).where(TalentRequest.client_id.in_(allowed_client_ids))
        return list(self.db.execute(stmt).scalars().all())

    def list_for_candidates(
        self, candidate_ids: list[int], *, allowed_client_ids: list[int] | None = None
    ) -> dict[int, list[Application]]:
        """Batch form of ``list_for_candidate``: every application for the
        given candidates (same portfolio scoping), grouped by candidate id.

        The Candidate Pool list previously ran ``list_for_candidate`` once
        per candidate; with a Lever-sized pool that N+1 pattern exceeded the
        gateway's 30 s proxy timeout. This issues one query per chunk of
        ids instead (chunked to stay well under driver bind-parameter
        limits)."""
        grouped: dict[int, list[Application]] = {cid: [] for cid in candidate_ids}
        chunk = 1000
        for start in range(0, len(candidate_ids), chunk):
            ids = candidate_ids[start : start + chunk]
            stmt = (
                select(Application)
                .options(joinedload(Application.talent_request).joinedload(TalentRequest.client))
                .where(Application.candidate_id.in_(ids))
                .order_by(Application.id)
            )
            if allowed_client_ids is not None:
                stmt = stmt.join(TalentRequest).where(
                    TalentRequest.client_id.in_(allowed_client_ids)
                )
            for app in self.db.execute(stmt).unique().scalars().all():
                grouped[app.candidate_id].append(app)
        return grouped

    def _scope_stmt(
        self,
        stmt,
        *,
        client_id: int | None,
        search: str | None = None,
        talent_request_id: int | None = None,
        allowed_client_ids: list[int] | None = None,
    ):
        stmt = stmt.join(TalentRequest, TalentRequest.id == Application.talent_request_id)
        if talent_request_id is not None:
            stmt = stmt.where(Application.talent_request_id == talent_request_id)
        if client_id is not None:
            stmt = stmt.where(TalentRequest.client_id == client_id, client_may_access_request())
        elif allowed_client_ids is not None:
            stmt = stmt.where(TalentRequest.client_id.in_(allowed_client_ids))
        if search:
            like = f"%{search}%"
            stmt = stmt.where(TalentRequest.designation.ilike(like))
        return stmt

    def list_for_scope(
        self,
        *,
        client_id: int | None,
        search: str | None = None,
        talent_request_id: int | None = None,
        allowed_client_ids: list[int] | None = None,
    ) -> list[Application]:
        stmt = select(Application).options(
            joinedload(Application.candidate),
            joinedload(Application.talent_request).joinedload(TalentRequest.client),
        )
        stmt = self._scope_stmt(
            stmt,
            client_id=client_id,
            search=search,
            talent_request_id=talent_request_id,
            allowed_client_ids=allowed_client_ids,
        )
        stmt = stmt.order_by(Application.updated_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def list_page(
        self,
        *,
        search: str | None = None,
        talent_request_id: int | None = None,
        status: str | None = None,
        offer_statuses: tuple[str, ...] = (),
        allowed_client_ids: list[int] | None = None,
        limit: int,
        offset: int,
    ) -> tuple[list[Application], int]:
        """Staff Applications table page + total. Same scoping/search as
        ``list_for_scope``; ``status`` is applied in SQL. ``status ==
        "OFFER"`` also matches Lever-sourced applications whose *stage* is
        OFFER while their status is one of ``offer_statuses`` (Lever carries
        the offer as a stage) — the rule the table previously applied in the
        browser. Ordered ``updated_at DESC, id DESC`` (stable)."""
        conds = []
        if status:
            cond = Application.status == status
            if status == "OFFER" and offer_statuses:
                cond = or_(
                    cond,
                    and_(
                        Application.current_stage == "OFFER",
                        Application.status.in_(offer_statuses),
                    ),
                )
            conds.append(cond)
        scope = dict(
            client_id=None,
            search=search.strip() if search and search.strip() else None,
            talent_request_id=talent_request_id,
            allowed_client_ids=allowed_client_ids,
        )
        total = self.db.execute(
            self._scope_stmt(select(func.count(Application.id)), **scope).where(*conds)
        ).scalar_one()
        stmt = self._scope_stmt(
            select(Application).options(
                joinedload(Application.candidate),
                joinedload(Application.talent_request).joinedload(TalentRequest.client),
            ),
            **scope,
        ).where(*conds)
        stmt = stmt.order_by(Application.updated_at.desc(), Application.id.desc())
        rows = self.db.execute(stmt.limit(limit).offset(offset)).unique().scalars().all()
        return list(rows), int(total)

    def active_counts_by_request(
        self,
        request_ids: list[int],
        statuses: set[str] | frozenset[str],
        *,
        client_visible_only: bool = False,
    ) -> dict[int, int]:
        """One GROUP BY query instead of loading every application (and its
        candidate) per request card just to count the active ones."""
        if not request_ids:
            return {}
        stmt = (
            select(Application.talent_request_id, func.count(Application.id))
            .where(
                Application.talent_request_id.in_(request_ids),
                Application.status.in_(list(statuses)),
            )
            .group_by(Application.talent_request_id)
        )
        if client_visible_only:
            stmt = stmt.where(Application.is_client_visible.is_(True))
        counts = {rid: 0 for rid in request_ids}
        counts.update({rid: n for rid, n in self.db.execute(stmt).all()})
        return counts

    def get_for_pair(
        self, candidate_id: int, talent_request_id: int
    ) -> Application | None:
        stmt = select(Application).where(
            Application.candidate_id == candidate_id,
            Application.talent_request_id == talent_request_id,
        )
        return self.db.execute(stmt).scalars().first()

    def exists_for_pair(self, candidate_id: int, talent_request_id: int) -> bool:
        stmt = select(Application.id).where(
            Application.candidate_id == candidate_id,
            Application.talent_request_id == talent_request_id,
        )
        return self.db.execute(stmt).scalars().first() is not None

    def map_for_requests(self, talent_request_ids) -> dict[tuple[int, int], Application]:
        """Every application on these requests, keyed by (candidate_id, talent_request_id)."""
        ids = sorted(set(talent_request_ids))
        if not ids:
            return {}
        stmt = select(Application).where(Application.talent_request_id.in_(ids))
        return {(a.candidate_id, a.talent_request_id): a for a in self.db.execute(stmt).scalars()}

    def add(self, application: Application) -> Application:
        self.db.add(application)
        self.db.flush()
        return application
