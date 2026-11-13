"""Regression: GET /api/talent/candidates (Candidate Pool) must not issue one
applications query per candidate.

Production (2026-11-13) showed the list endpoint never completing before the
shell-web gateway's 30 s proxy timeout ("Failed to proxy ... socket hang up")
once the pool held the Lever-sized candidate set, because the route called
``CandidateService.to_out`` (one ``list_for_candidate`` query) per candidate.
"""

from contextlib import contextmanager

from sqlalchemy import event

from app.db.session import engine
from app.schemas.application import ApplicationCreate
from app.schemas.talent_request import TalentRequestCreate
from app.services.application_service import ApplicationService
from app.services.candidate_service import CandidateService
from app.services.talent_request_service import TalentRequestService
from tests.conftest import headers_for


@contextmanager
def _count_queries():
    counter = {"n": 0}

    def _on_execute(*_args, **_kwargs):
        counter["n"] += 1

    event.listen(engine, "before_cursor_execute", _on_execute)
    try:
        yield counter
    finally:
        event.remove(engine, "before_cursor_execute", _on_execute)


def _seed(db, world, n_candidates: int):
    requests = TalentRequestService(db)
    abc_req = requests.create_request(
        client_id=world["abc"].id, created_by=world["abc_user_id"],
        payload=TalentRequestCreate(designation="Role A", description="d", required_skills=[]),
    )
    xyz_req = requests.create_request(
        client_id=world["xyz"].id, created_by=world["xyz_user_id"],
        payload=TalentRequestCreate(designation="Role B", description="d", required_skills=[]),
    )
    cands = CandidateService(db)
    apps = ApplicationService(db)
    for i in range(n_candidates):
        c, _ = cands.upsert_from_source(
            lever_external_id=f"lever-{i}", full_name=f"Candidate {i:03d}",
            email=None, headline="Engineer",
        )
        db.flush()
        apps.create_application(
            actor_id=world["ta_user_id"],
            payload=ApplicationCreate(candidate_id=c.id, talent_request_id=abc_req.id),
        )
        if i % 2 == 0:  # half also apply to the second client (one master record)
            apps.create_application(
                actor_id=world["ta_user_id"],
                payload=ApplicationCreate(candidate_id=c.id, talent_request_id=xyz_req.id),
            )
    db.commit()


def _list_query_count(api_client, headers) -> tuple[int, list]:
    with _count_queries() as counter:
        resp = api_client.get("/api/talent/candidates", headers=headers)
    assert resp.status_code == 200
    return counter["n"], resp.json()


def test_candidate_pool_query_count_does_not_grow_with_candidates(api_client, db, two_tenant_world):
    _seed(db, two_tenant_world, 3)
    small, body_small = _list_query_count(api_client, two_tenant_world["ta_headers"])
    _seed_more = 40
    # add more candidates against fresh requests
    _seed(db, two_tenant_world, 0)
    cands = CandidateService(db)
    apps = ApplicationService(db)
    req_id = body_small[0]["applications"][0]["application_id"]
    from app.models.application import Application

    abc_request_id = db.get(Application, req_id).talent_request_id
    for i in range(_seed_more):
        c, _ = cands.upsert_from_source(
            lever_external_id=f"more-{i}", full_name=f"More {i:03d}", email=None, headline="",
        )
        db.flush()
        apps.create_application(
            actor_id=two_tenant_world["ta_user_id"],
            payload=ApplicationCreate(candidate_id=c.id, talent_request_id=abc_request_id),
        )
    db.commit()

    large, body_large = _list_query_count(api_client, two_tenant_world["ta_headers"])
    assert len(body_large) == len(body_small) + _seed_more
    # Constant, not linear: 40 extra candidates must not add 40 extra queries.
    assert large == small, (small, large)


def test_batched_output_matches_per_candidate_output(db, two_tenant_world):
    _seed(db, two_tenant_world, 5)
    service = CandidateService(db)
    candidates = service.repo.list_all()
    batched = service.to_out_many(candidates)
    single = [service.to_out(c) for c in candidates]
    assert [b.model_dump() for b in batched] == [s.model_dump() for s in single]
    assert any(len(b.applications) == 2 for b in batched)


def test_candidate_pool_batch_respects_portfolio_scope(api_client, db, two_tenant_world):
    _seed(db, two_tenant_world, 4)
    scoped = headers_for(
        two_tenant_world["ta_user_id"], full_name="Portfolio TA", role="TA_MEMBER",
        client_ids=[two_tenant_world["abc"].id],
    )
    resp = api_client.get("/api/talent/candidates", headers=scoped)
    assert resp.status_code == 200
    for cand in resp.json():
        assert cand["applications"], cand["id"]
        assert {a["designation"] for a in cand["applications"]} == {"Role A"}


def test_candidate_pool_still_forbidden_for_client_persona(api_client, db, two_tenant_world):
    _seed(db, two_tenant_world, 1)
    resp = api_client.get("/api/talent/candidates", headers=two_tenant_world["abc_headers"])
    assert resp.status_code == 403
