"""Server-side pagination for All Requests, Applications and Recruitment
Postings (``/paged`` endpoints). The legacy unpaginated endpoints are kept
and must behave exactly as before."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.posting_client_mapping import PostingClientMapping
from app.models.recruitment_posting_ref import RecruitmentPostingRef
from app.models.talent_request import TalentRequest
from app.schemas.application import ApplicationCreate
from app.schemas.talent_request import TalentRequestCreate
from app.services.application_service import ApplicationService
from app.services.candidate_service import CandidateService
from app.services.talent_request_service import TalentRequestService
from tests.conftest import headers_for
from tests.test_candidate_pool_list_performance import _count_queries


def _portfolio(world, client):
    return headers_for(world["ta_user_id"], full_name="Portfolio TA", role="TA_MEMBER", client_ids=[client.id])


# ---------------------------------------------------------------- requests

REQ = "/api/talent/requests/paged"


@pytest.fixture
def requests_world(db, two_tenant_world):
    """30 ABC + 7 XYZ requests. Every 3rd ABC request is IN_PROGRESS, every
    5th APPROVED; ABC request #0 has 2 active + 1 rejected application, one
    of the active ones client-visible. One extra ABC request is promoted from
    a posting with NO verified mapping — hidden from the ABC client."""
    w = two_tenant_world
    rs = TalentRequestService(db)
    made = {"abc": [], "xyz": []}
    for key, n in (("abc", 30), ("xyz", 7)):
        for i in range(n):
            r = rs.create_request(
                client_id=w[key].id, created_by=w[f"{key}_user_id"],
                payload=TalentRequestCreate(
                    designation=f"{key.upper()} Role {i:02d}" + (" Python" if i % 4 == 0 else ""),
                    description="d", required_skills=[],
                ),
            )
            if i % 3 == 0:
                r.lifecycle_status = "IN_PROGRESS"
            elif i % 5 == 0:
                r.lifecycle_status = "APPROVED"
            made[key].append(r)
    db.flush()
    # identical created_at for a block of requests -> ordering must tie-break on id
    same = datetime(2026, 1, 1, tzinfo=UTC)
    for r in made["abc"][:6]:
        r.created_at = same
    hidden = TalentRequest(
        request_code="TA-HIDDEN", client_id=w["abc"].id, designation="Hidden Promoted",
        description="", posting_external_id="ext-hidden", provider="LEVER", created_by=w["ta_user_id"],
    )
    db.add(hidden)
    cs, apps = CandidateService(db), ApplicationService(db)
    first = made["abc"][0]
    for i, (status, visible) in enumerate((("ACTIVE", True), ("SHORTLISTED", False), ("REJECTED", True))):
        c, _ = cs.upsert_from_source(lever_external_id=f"rq{i}", full_name=f"Req Cand {i}", email=None, headline="")
        db.flush()
        a = apps.create_application(
            actor_id=w["ta_user_id"], payload=ApplicationCreate(candidate_id=c.id, talent_request_id=first.id)
        )
        a.status, a.is_client_visible = status, visible
    db.commit()
    return {"first_id": first.id, "abc_visible": 30, "abc_staff": 31, "xyz": 7, "total": 38}


def test_requests_default_12_and_total(api_client, requests_world, two_tenant_world):
    body = api_client.get(REQ, headers=two_tenant_world["ta_headers"]).json()
    assert (body["page"], body["page_size"], len(body["items"])) == (1, 12, 12)
    assert body["total"] == requests_world["total"]
    assert body["total_pages"] == 4


@pytest.mark.parametrize("size", [12, 24, 48, 96])
def test_requests_card_page_sizes(api_client, requests_world, two_tenant_world, size):
    body = api_client.get(REQ, headers=two_tenant_world["ta_headers"], params={"page_size": size}).json()
    assert len(body["items"]) == min(size, requests_world["total"])


@pytest.mark.parametrize("size", [10, 20, 0, 13, 1000])
def test_requests_rejects_other_sizes(api_client, requests_world, two_tenant_world, size):
    r = api_client.get(REQ, headers=two_tenant_world["ta_headers"], params={"page_size": size})
    assert r.status_code == 422


def test_requests_pages_complete_stable_and_bounded(api_client, requests_world, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    seen = []
    for p in range(1, 5):
        seen += [r["id"] for r in api_client.get(REQ, headers=h, params={"page": p}).json()["items"]]
    assert len(seen) == len(set(seen)) == requests_world["total"]
    again = []
    for p in range(1, 5):
        again += [r["id"] for r in api_client.get(REQ, headers=h, params={"page": p}).json()["items"]]
    assert again == seen
    past = api_client.get(REQ, headers=h, params={"page": 5}).json()
    assert past["items"] == [] and past["total"] == requests_world["total"]
    assert api_client.get(REQ, headers=h, params={"page": 0}).status_code == 422


def test_requests_search_stage_status_and_active_server_side(api_client, requests_world, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    # "Python" on every 4th of 30 ABC (8) + every 4th of 7 XYZ (2)
    assert api_client.get(REQ, headers=h, params={"search": "python"}).json()["total"] == 10
    in_progress = api_client.get(REQ, headers=h, params={"status_filter": "IN_PROGRESS"}).json()
    assert in_progress["total"] == 10 + 3  # i%3==0 over 30 and 7
    active = api_client.get(REQ, headers=h, params={"status_filter": "active", "page_size": 96}).json()
    assert {r["lifecycle_status"] for r in active["items"]} <= {"APPROVED", "IN_PROGRESS"}
    approved = api_client.get(REQ, headers=h, params={"status_filter": "APPROVED"}).json()["total"]
    assert active["total"] == in_progress["total"] + approved
    staged = api_client.get(REQ, headers=h, params={"stage": "REQUEST_SUBMITTED", "page_size": 96}).json()
    assert all(r["current_stage"] == "REQUEST_SUBMITTED" for r in staged["items"])


def test_requests_active_counts_match_legacy_and_use_constant_queries(api_client, requests_world, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    legacy = {r["id"]: r for r in api_client.get("/api/talent/requests", headers=h).json()}
    paged = api_client.get(REQ, headers=h, params={"page_size": 96}).json()["items"]
    assert all(p == legacy[p["id"]] for p in paged)  # identical card payload
    first = next(p for p in paged if p["id"] == requests_world["first_id"])
    assert first["active_application_count"] == 2
    with _count_queries() as small:
        api_client.get(REQ, headers=h, params={"page_size": 12})
    with _count_queries() as large:
        api_client.get(REQ, headers=h, params={"page_size": 48})
    assert small["n"] == large["n"]


def test_requests_client_tenant_isolation(api_client, requests_world, two_tenant_world):
    w = two_tenant_world
    abc = api_client.get(REQ, headers=w["abc_headers"], params={"page_size": 96}).json()
    assert abc["total"] == requests_world["abc_visible"]  # promoted-without-mapping request hidden
    assert all(r["client_id"] == w["abc"].id for r in abc["items"])
    # a client cannot widen scope with client_id
    sneaky = api_client.get(REQ, headers=w["abc_headers"], params={"client_id": w["xyz"].id}).json()
    assert sneaky["total"] == requests_world["abc_visible"]
    # client view: staff-only fields blanked, count = shared active only
    first = next(r for r in abc["items"] if r["id"] == requests_world["first_id"])
    assert first["active_application_count"] == 1
    assert first["ta_status"] == "" and first["notes"] == ""
    legacy = {r["id"]: r for r in api_client.get("/api/talent/requests", headers=w["abc_headers"]).json()}
    assert all(r == legacy[r["id"]] for r in abc["items"])


def test_requests_portfolio_scope(api_client, requests_world, two_tenant_world):
    w = two_tenant_world
    body = api_client.get(REQ, headers=_portfolio(w, w["xyz"]), params={"page_size": 96}).json()
    assert body["total"] == requests_world["xyz"]
    assert all(r["client_id"] == w["xyz"].id for r in body["items"])


def test_requests_empty_and_unauthenticated(api_client, db, two_tenant_world):
    body = api_client.get(REQ, headers=two_tenant_world["ta_headers"]).json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 12, "total_pages": 1}
    assert api_client.get(REQ).status_code in (401, 403)


# ------------------------------------------------------------ applications

APP = "/api/talent/applications/paged"


@pytest.fixture
def apps_world(db, two_tenant_world):
    """45 ABC applications (statuses cycle) + 6 XYZ; 2 ABC ones are Lever
    offers carried as stage=OFFER with status ACTIVE."""
    w = two_tenant_world
    rs, cs, apps = TalentRequestService(db), CandidateService(db), ApplicationService(db)
    reqs = {
        k: rs.create_request(client_id=w[k].id, created_by=w[f"{k}_user_id"],
            payload=TalentRequestCreate(designation=f"{k.upper()} Engineer", description="d", required_skills=[]))
        for k in ("abc", "xyz")
    }
    statuses = ["ACTIVE", "SHORTLISTED", "REJECTED", "OFFER", "CLIENT_REVIEW"]
    base = datetime(2026, 3, 1, tzinfo=UTC)
    for key, n in (("abc", 45), ("xyz", 6)):
        for i in range(n):
            c, _ = cs.upsert_from_source(
                lever_external_id=f"{key}-a{i}", full_name=f"{key} cand {i:02d}", email=None, headline=""
            )
            db.flush()
            a = apps.create_application(actor_id=w["ta_user_id"],
                payload=ApplicationCreate(candidate_id=c.id, talent_request_id=reqs[key].id))
            a.status = statuses[i % 5]
            a.updated_at = base + timedelta(minutes=i // 3)  # ties of 3 -> id tie-break
            if key == "abc" and i in (0, 5):
                a.current_stage, a.status = "OFFER", "ACTIVE"
    db.commit()
    return {"total": 51, "abc": 45, "xyz": 6}


def test_applications_default_20(api_client, apps_world, two_tenant_world):
    body = api_client.get(APP, headers=two_tenant_world["ta_headers"]).json()
    assert (body["page_size"], len(body["items"]), body["total"], body["total_pages"]) == (20, 20, 51, 3)


@pytest.mark.parametrize("size", [20, 50, 100])
def test_applications_table_sizes(api_client, apps_world, two_tenant_world, size):
    body = api_client.get(APP, headers=two_tenant_world["ta_headers"], params={"page_size": size}).json()
    assert len(body["items"]) == min(size, 51)


@pytest.mark.parametrize("size", [10, 12, 25, 200])
def test_applications_rejects_other_sizes(api_client, apps_world, two_tenant_world, size):
    assert api_client.get(APP, headers=two_tenant_world["ta_headers"], params={"page_size": size}).status_code == 422


def test_applications_pages_stable_and_complete(api_client, apps_world, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    ids = []
    for p in (1, 2, 3):
        ids += [a["id"] for a in api_client.get(APP, headers=h, params={"page": p}).json()["items"]]
    assert len(ids) == len(set(ids)) == 51
    last = api_client.get(APP, headers=h, params={"page": 3}).json()
    assert len(last["items"]) == 11


def test_applications_offer_filter_server_side(api_client, apps_world, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    body = api_client.get(APP, headers=h, params={"status_filter": "OFFER", "page_size": 100}).json()
    # status OFFER: i%5==3 -> abc 9 (i=3..43), xyz 1 (i=3); plus 2 stage-OFFER/ACTIVE
    assert body["total"] == 9 + 1 + 2
    assert all(a["status"] == "OFFER" or a["current_stage"] == "OFFER" for a in body["items"])
    rej = api_client.get(APP, headers=h, params={"status_filter": "REJECTED"}).json()
    assert all(a["status"] == "REJECTED" for a in rej["items"])


def test_applications_search_request_filter_and_legacy_parity(api_client, apps_world, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    assert api_client.get(APP, headers=h, params={"search": "XYZ Engineer"}).json()["total"] == 6
    legacy = api_client.get("/api/talent/applications", headers=h).json()
    paged = api_client.get(APP, headers=h, params={"page_size": 100}).json()["items"]
    assert sorted(a["id"] for a in legacy) == sorted(a["id"] for a in paged)
    by_id = {a["id"]: a for a in legacy}
    assert all(a == by_id[a["id"]] for a in paged)
    rid = paged[0]["talent_request_id"]
    one = api_client.get(APP, headers=h, params={"talent_request_id": rid, "page_size": 100}).json()
    assert all(a["talent_request_id"] == rid for a in one["items"])


def test_applications_portfolio_scope_and_client_forbidden(api_client, apps_world, two_tenant_world):
    w = two_tenant_world
    body = api_client.get(APP, headers=_portfolio(w, w["xyz"]), params={"page_size": 100}).json()
    assert body["total"] == 6 and {a["client_name"] for a in body["items"]} == {"XYZ Company"}
    assert api_client.get(APP, headers=w["abc_headers"]).status_code == 403
    assert api_client.get(APP).status_code in (401, 403)


def test_applications_query_count_constant(api_client, apps_world, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    with _count_queries() as small:
        api_client.get(APP, headers=h, params={"page_size": 20})
    with _count_queries() as large:
        api_client.get(APP, headers=h, params={"page_size": 100})
    assert small["n"] == large["n"]


# ---------------------------------------------------------------- postings

POST = "/api/talent/postings/paged"


@pytest.fixture
def postings_world(db, two_tenant_world):
    """60 postings: 40 closed + 20 published. Mappings: 8 VERIFIED to ABC
    (2 MANUAL), 3 VERIFIED to XYZ, 5 needs-review (unmapped, UNKNOWN id),
    4 REJECTED (no client), rest have no mapping row."""
    w = two_tenant_world
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    refs = []
    for i in range(60):
        ref = RecruitmentPostingRef(
            provider="LEVER", external_id=f"p{i:02d}", title=f"Posting {i:02d}" + (" Data" if i % 6 == 0 else ""),
            state="closed" if i < 40 else "published", location="Colombo" if i % 2 else "Remote",
            last_seen_at=None if i in (7, 8) else t0 + timedelta(hours=i // 2),
        )
        db.add(ref)
        refs.append(ref)
    db.flush()

    def mapping(i, **kw):
        db.add(PostingClientMapping(provider="LEVER", posting_external_id=f"p{i:02d}", **kw))

    for i in range(8):
        mapping(i * 5 + 1, status="VERIFIED", client_id=w["abc"].id,
                source="MANUAL" if i < 2 else "LEVER_DTC_TAG", resolution_status="RESOLVED")
    for i in (2, 44, 52):
        mapping(i, status="VERIFIED", client_id=w["xyz"].id, source="LEVER_DTC_TAG", resolution_status="RESOLVED")
    for i in (3, 13, 23, 43, 53):
        mapping(i, status="UNMAPPED", client_id=None, source="", resolution_status="UNKNOWN_CLIENT_IDENTIFIER")
    for i in (4, 14, 24, 54):
        mapping(i, status="REJECTED", client_id=None, source="MANUAL", resolution_status="NO_DTC_TAG")
    db.commit()
    return {"all": 60, "active": 20, "verified": 11, "review": 5, "rejected": 4}


def test_postings_default_view_size_and_counts(api_client, postings_world, two_tenant_world):
    body = api_client.get(POST, headers=two_tenant_world["ta_headers"]).json()
    assert (body["page_size"], len(body["items"]), body["total"]) == (20, 20, 20)  # Recent/Active default
    assert all(p["state"] != "closed" for p in body["items"])
    c = body["counts"]
    assert (c["all"], c["active"], c["verified"], c["review"]) == (60, 20, 11, 5)
    assert c["unmapped"] == 60 - 11 - 4  # no-row postings count as unmapped; REJECTED does not


@pytest.mark.parametrize("view", ["active", "verified", "unmapped", "review", "all"])
def test_postings_views_match_legacy_client_side_filters(api_client, postings_world, two_tenant_world, view):
    """The SQL views must select exactly what the old browser filters did."""
    h = two_tenant_world["ta_headers"]
    legacy = api_client.get("/api/talent/postings", headers=h).json()
    from app.repositories.posting_repo import NEEDS_REVIEW_RESOLUTIONS

    review = set(NEEDS_REVIEW_RESOLUTIONS)
    match = {
        "active": lambda p: p["state"] != "closed",
        "verified": lambda p: p["mapping_status"] == "VERIFIED",
        "unmapped": lambda p: p["mapping_status"] == "UNMAPPED",
        "review": lambda p: p["mapping_status"] != "VERIFIED" and p["resolution_status"] in review,
        "all": lambda p: True,
    }[view]
    expected = {p["id"]: p for p in legacy if match(p)}
    got = []
    page = 1
    while True:
        body = api_client.get(POST, headers=h, params={"view": view, "page": page, "page_size": 100}).json()
        got += body["items"]
        if page >= body["total_pages"]:
            break
        page += 1
    assert body["total"] == len(expected) == body["counts"][view]
    assert {p["id"] for p in got} == set(expected)
    assert all(p == expected[p["id"]] for p in got)  # identical rows incl. client name


def test_postings_ordering_stable_with_null_last_seen(api_client, postings_world, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    ids = []
    for p in (1, 2, 3):
        ids += [x["id"] for x in api_client.get(POST, headers=h, params={"view": "all", "page": p}).json()["items"]]
    assert len(ids) == len(set(ids)) == 60
    assert ids == [x["id"] for x in api_client.get(POST, headers=h, params={"view": "all", "page_size": 100}).json()["items"]]


def test_postings_search_resets_counts(api_client, postings_world, two_tenant_world):
    body = api_client.get(POST, headers=two_tenant_world["ta_headers"], params={"view": "all", "search": "data"}).json()
    assert body["total"] == 10 == body["counts"]["all"]  # i % 6 == 0 over 60
    assert all("Data" in p["title"] for p in body["items"])


def test_postings_portfolio_scope_matches_legacy(api_client, postings_world, two_tenant_world):
    w = two_tenant_world
    h = _portfolio(w, w["abc"])
    legacy_ids = {p["id"] for p in api_client.get("/api/talent/postings", headers=h).json()}
    body = api_client.get(POST, headers=h, params={"view": "all", "page_size": 100}).json()
    assert {p["id"] for p in body["items"]} == legacy_ids
    assert body["total"] == 60 - 3  # the three XYZ-verified postings are hidden
    assert all(p["mapping_client_name"] in (None, "ABC Company") for p in body["items"])


def test_postings_validation_and_authorization(api_client, postings_world, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    assert api_client.get(POST, headers=h, params={"view": "nope"}).status_code == 422
    assert api_client.get(POST, headers=h, params={"page_size": 12}).status_code == 422
    assert api_client.get(POST, headers=two_tenant_world["abc_headers"]).status_code == 403
    assert api_client.get(POST).status_code in (401, 403)


def test_postings_query_count_constant(api_client, postings_world, two_tenant_world):
    h = two_tenant_world["ta_headers"]
    with _count_queries() as small:
        api_client.get(POST, headers=h, params={"view": "all", "page_size": 20})
    with _count_queries() as large:
        api_client.get(POST, headers=h, params={"view": "all", "page_size": 100})
    assert small["n"] == large["n"]
