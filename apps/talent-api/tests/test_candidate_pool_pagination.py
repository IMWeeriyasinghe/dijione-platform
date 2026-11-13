"""Server-side Candidate Pool pagination: GET /api/talent/candidates/paged."""

import pytest

from app.schemas.application import ApplicationCreate
from app.schemas.talent_request import TalentRequestCreate
from app.services.application_service import ApplicationService
from app.services.candidate_service import CandidateService
from app.services.talent_request_service import TalentRequestService
from tests.conftest import headers_for
from tests.test_candidate_pool_list_performance import _count_queries

URL = "/api/talent/candidates/paged"


@pytest.fixture
def pool(db, two_tenant_world):
    """105 candidates on ABC (names padded so ordering is predictable),
    5 more only on XYZ, plus 3 sharing one name to test tie-break order."""
    w = two_tenant_world
    rs = TalentRequestService(db)
    abc = rs.create_request(client_id=w["abc"].id, created_by=w["abc_user_id"],
        payload=TalentRequestCreate(designation="Role A", description="d", required_skills=[]))
    xyz = rs.create_request(client_id=w["xyz"].id, created_by=w["xyz_user_id"],
        payload=TalentRequestCreate(designation="Role B", description="d", required_skills=[]))
    cs, apps = CandidateService(db), ApplicationService(db)

    def add(ext, name, title, req):
        c, _ = cs.upsert_from_source(lever_external_id=ext, full_name=name, email=None, headline=title)
        db.flush()
        apps.create_application(actor_id=w["ta_user_id"],
            payload=ApplicationCreate(candidate_id=c.id, talent_request_id=req.id))

    for i in range(105):
        add(f"a{i}", f"Abc Person {i:03d}", "Python Developer" if i % 10 == 0 else "Analyst", abc)
    for i in range(5):
        add(f"x{i}", f"Xyz Person {i:03d}", "Analyst", xyz)
    for i in range(3):
        add(f"t{i}", "Same Name", "Analyst", abc)
    db.commit()
    return {"total": 113, "abc_total": 108}


def _get(api_client, headers, **params):
    return api_client.get(URL, headers=headers, params=params)


def test_default_page_size_is_12(api_client, pool, two_tenant_world):
    r = _get(api_client, two_tenant_world["ta_headers"])
    assert r.status_code == 200
    body = r.json()
    assert (body["page"], body["page_size"], len(body["items"])) == (1, 12, 12)
    assert body["total"] == pool["total"]
    assert body["total_pages"] == 10  # ceil(113 / 12)


@pytest.mark.parametrize("size", [12, 24, 48, 96])
def test_allowed_page_sizes(api_client, pool, two_tenant_world, size):
    body = _get(api_client, two_tenant_world["ta_headers"], page_size=size).json()
    assert len(body["items"]) == min(size, pool["total"])
    assert body["total_pages"] == -(-pool["total"] // size)


@pytest.mark.parametrize("size", [10, 20, 50, 100])
def test_legacy_page_sizes_still_accepted(api_client, pool, two_tenant_world, size):
    """Backward compatibility with the original #106 sizes."""
    body = _get(api_client, two_tenant_world["ta_headers"], page_size=size).json()
    assert body["page_size"] == size
    assert len(body["items"]) == min(size, pool["total"])


@pytest.mark.parametrize("size", [0, 5, 11, 25, 36, 101, 1000])
def test_rejects_other_page_sizes(api_client, pool, two_tenant_world, size):
    assert _get(api_client, two_tenant_world["ta_headers"], page_size=size).status_code == 422


def test_rejects_page_below_one(api_client, pool, two_tenant_world):
    assert _get(api_client, two_tenant_world["ta_headers"], page=0).status_code == 422


def test_last_page_and_past_end(api_client, pool, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    last = _get(api_client, h, page=10).json()
    assert len(last["items"]) == 5  # 113 - 9 * 12
    past = _get(api_client, h, page=11).json()
    assert past["items"] == [] and past["total"] == pool["total"]


def test_pages_are_stable_complete_and_non_overlapping(api_client, pool, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    seen = []
    for p in range(1, 11):
        seen += [c["id"] for c in _get(api_client, h, page=p).json()["items"]]
    assert len(seen) == len(set(seen)) == pool["total"]
    # identical when re-fetched, including the three same-name candidates
    again = []
    for p in range(1, 11):
        again += [c["id"] for c in _get(api_client, h, page=p).json()["items"]]
    assert again == seen
    full = _get(api_client, h, page_size=96).json()["items"] + _get(api_client, h, page_size=96, page=2).json()["items"]
    names = [(c["full_name"], c["id"]) for c in full]
    assert names == sorted(names)


def test_search_spans_all_records_and_counts_matches(api_client, pool, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    body = _get(api_client, h, search="python").json()  # case-insensitive, on title
    assert body["total"] == 11  # i = 0,10,...,100 — includes records far past page 1
    assert len(body["items"]) == 11
    assert any(c["full_name"] == "Abc Person 100" for c in body["items"])  # beyond default page 1 unfiltered
    page2 = _get(api_client, h, search="python", page_size=10, page=2).json()  # legacy size still pages search
    assert [c["full_name"] for c in page2["items"]] == ["Abc Person 100"]
    assert _get(api_client, h, search="Xyz Person").json()["total"] == 5


def test_empty_result(api_client, pool, two_tenant_world):
    body = _get(api_client, two_tenant_world["ta_headers"], search="no-such-candidate").json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 12, "total_pages": 1}


def test_empty_pool(api_client, db, two_tenant_world):
    body = _get(api_client, two_tenant_world["ta_headers"]).json()
    assert body["total"] == 0 and body["items"] == []


def test_portfolio_scope_is_enforced_in_items_and_total(api_client, pool, two_tenant_world):
    w = two_tenant_world
    scoped = headers_for(w["ta_user_id"], full_name="Portfolio TA", role="TA_MEMBER", client_ids=[w["abc"].id])
    body = _get(api_client, scoped, page_size=96).json()
    assert body["total"] == pool["abc_total"]
    assert not any(c["full_name"].startswith("Xyz") for c in body["items"])
    assert _get(api_client, scoped, search="Xyz").json()["total"] == 0


def test_client_persona_forbidden(api_client, pool, two_tenant_world):
    assert _get(api_client, two_tenant_world["abc_headers"]).status_code == 403
    assert api_client.get(URL).status_code in (401, 403)


def test_legacy_list_and_detail_unchanged(api_client, pool, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    legacy = api_client.get("/api/talent/candidates", headers=h)
    assert legacy.status_code == 200 and isinstance(legacy.json(), list)
    assert len(legacy.json()) == pool["total"]
    first = _get(api_client, h).json()["items"][0]
    detail = api_client.get(f"/api/talent/candidates/{first['id']}", headers=h).json()
    assert detail == first  # same CandidateOut shape


def test_query_count_independent_of_page_size(api_client, pool, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    with _count_queries() as small:
        _get(api_client, h, page_size=12)
    with _count_queries() as large:
        _get(api_client, h, page_size=96)
    assert small["n"] == large["n"]
