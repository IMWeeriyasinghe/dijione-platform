"""A verified posting's candidacies are read completely, or not used at all."""

import time
import warnings

import pytest

from app.db.session import engine
from app.models.application import Application
from app.models.audit_outbox import AuditOutbox
from app.models.candidate import Candidate
from app.models.posting_client_mapping import PostingClientMapping
from app.models.talent_request import TalentRequest
from app.services import recruitment_consumer_service as consumer
from tests.conftest import FakeRecruitmentClient, recruitment_candidacy_dto, recruitment_posting_dto

URL = "/api/talent/internal/recruitment/reconcile"
HEADERS = {"X-Internal-Token": "test-only-internal-secret"}


def _posting(client_name, external_id="p1"):
    return recruitment_posting_dto(
        external_id, title="Engineer", dtc_status="OK", dtc_client_name=client_name, dtc_raw_tag=f"DTC - {client_name}",
    )


def _rows(count, posting="p1", prefix="o"):
    return [
        recruitment_candidacy_dto(f"{prefix}{i:06}", posting_external_id=posting, candidate_external_id=f"{prefix}c{i:06}")
        for i in range(count)
    ]


def _run(api_client, monkeypatch, source):
    monkeypatch.setattr("app.api.routes.recruitment.get_recruitment_batch_client", lambda: source)
    return api_client.post(URL, headers=HEADERS)


def _count(db, model):
    db.expire_all()
    return db.query(model).count()


@pytest.mark.parametrize(("count", "requests"), [(0, 1), (1, 2), (499, 2), (500, 2), (501, 3), (1000, 3), (2090, 6)])
def test_every_candidacy_is_read_across_page_boundaries(api_client, db, two_tenant_world, monkeypatch, count, requests):
    source = FakeRecruitmentClient([_posting(two_tenant_world["abc"].name)], candidacies=_rows(count))
    body = _run(api_client, monkeypatch, source).json()
    assert body["outcome"] == "SUCCEEDED"
    assert body["counts"]["promotion"]["candidacies_seen"] == count
    assert source.page_calls == requests
    assert _count(db, Application) == count


def test_a_failed_later_page_uses_no_candidacies_and_a_retry_completes(api_client, db, two_tenant_world, monkeypatch):
    source = FakeRecruitmentClient([_posting(two_tenant_world["abc"].name)], candidacies=_rows(1200))
    source.fail_on_page = 2
    body = _run(api_client, monkeypatch, source).json()
    assert body["outcome"] == "FAILED" and body["reasons"] == ["candidacies_unavailable"]
    assert _count(db, Application) == 0

    source.fail_on_page = None
    source.page_calls = 0
    assert _run(api_client, monkeypatch, source).json()["outcome"] == "SUCCEEDED"
    assert _count(db, Application) == 1200


def test_a_failed_read_keeps_existing_applications_unchanged(api_client, db, two_tenant_world, monkeypatch):
    source = FakeRecruitmentClient([_posting(two_tenant_world["abc"].name)], candidacies=_rows(600))
    assert _run(api_client, monkeypatch, source).json()["outcome"] == "SUCCEEDED"
    first = db.query(Application).first()
    first.is_client_visible = True
    db.commit()

    source.page_calls = 0
    source.fail_on_page = 2
    assert _run(api_client, monkeypatch, source).json()["outcome"] == "FAILED"
    assert _count(db, Application) == 600
    assert db.query(Application).filter(Application.is_client_visible.is_(True)).count() == 1


def test_a_rerun_is_idempotent_and_keeps_new_applications_unshared(api_client, db, two_tenant_world, monkeypatch):
    source = FakeRecruitmentClient([_posting(two_tenant_world["abc"].name)], candidacies=_rows(1100))
    for _ in range(2):
        source.page_calls = 0
        assert _run(api_client, monkeypatch, source).json()["outcome"] == "SUCCEEDED"
    assert _count(db, Application) == 1100 and _count(db, Candidate) == 1100
    assert db.query(Application).filter(Application.is_client_visible.is_(True)).count() == 0


class _Scripted(FakeRecruitmentClient):
    def __init__(self, postings, pages):
        super().__init__(postings)
        self.pages = iter(pages)

    def list_candidacies_page(self, **kwargs):
        return next(self.pages)


@pytest.mark.parametrize(
    "pages",
    [
        pytest.param(lambda r: [r[:2], r[:2]], id="source_ignores_the_cursor"),
        pytest.param(lambda r: [r[:2], r[1:3]], id="row_repeated_across_pages"),
        pytest.param(lambda r: [_rows(2, posting="other")], id="row_from_another_posting"),
        pytest.param(lambda r: [_rows(501)], id="oversized_page"),
        pytest.param(lambda r: [[{**r[0], "external_id": ""}]], id="row_without_an_id"),
    ],
)
def test_an_unprovable_read_is_refused_not_truncated(api_client, db, two_tenant_world, monkeypatch, pages):
    source = _Scripted([_posting(two_tenant_world["abc"].name)], pages(_rows(3)))
    body = _run(api_client, monkeypatch, source).json()
    assert body["outcome"] == "FAILED" and body["reasons"] == ["candidacies_unavailable"]
    assert _count(db, Application) == 0


def test_the_read_is_bounded_when_pages_never_end():
    class Endless:
        calls = 0

        def list_candidacies_page(self, *, posting_external_id, after_external_id, limit):
            Endless.calls += 1
            return _rows(1, prefix=f"x{Endless.calls}-")

    with pytest.raises(consumer.CandidacyReadIncomplete):
        consumer.read_all_candidacies(Endless(), "p1", lambda: None)
    assert Endless.calls == consumer.CANDIDACY_MAX_PAGES + 1


def test_only_verified_postings_are_read(api_client, db, two_tenant_world, monkeypatch):
    postings = [_posting(two_tenant_world["abc"].name), _posting("No Such Client", "p2")]
    source = FakeRecruitmentClient(postings, candidacies=_rows(3) + _rows(3, posting="p2", prefix="z"))
    body = _run(api_client, monkeypatch, source).json()
    assert body["counts"]["promotion"]["candidacies_seen"] == 3
    assert _count(db, Application) == 3


def test_the_budget_stops_a_slow_read_with_nothing_committed(db, two_tenant_world):
    source = FakeRecruitmentClient([_posting(two_tenant_world["abc"].name)], candidacies=_rows(1200))
    body = consumer.run_reconcile(db, client=source, budget_seconds=-1)
    assert body["outcome"] == "FAILED" and body["reasons"] == ["ReconcileBudgetExceeded"]
    assert _count(db, Application) == 0


def _untagged(external_id):
    return recruitment_posting_dto(external_id, title="Engineer", dtc_status="NO_TAG")


def _shared_world(db, api_client, monkeypatch, world):
    """p1 and p2 promoted for one client, every candidate shared."""
    name = world["abc"].name
    source = FakeRecruitmentClient(
        [_posting(name, "p1"), _posting(name, "p2")], candidacies=_rows(3, "p1", "a") + _rows(3, "p2", "b"),
    )
    assert _run(api_client, monkeypatch, source).json()["outcome"] == "SUCCEEDED"
    for application in db.query(Application).all():
        application.is_client_visible = True
    db.commit()
    return name


def _state(db):
    db.expire_all()
    return (
        sorted((m.posting_external_id, m.status, m.client_id, m.source) for m in db.query(PostingClientMapping).all()),
        sorted((r.posting_external_id, r.client_id, r.provider, r.lifecycle_status) for r in db.query(TalentRequest).all()),
        sorted((a.candidate_id, a.talent_request_id, a.is_client_visible) for a in db.query(Application).all()),
    )


def _change_everything(world, name):
    """p1 loses its tag, p2 moves to another client, p3 is new."""
    return [_untagged("p1"), _posting(world["xyz"].name, "p2"), _posting(name, "p3")]


@pytest.mark.parametrize("failure", ["down", "later_page", "unprovable"])
def test_a_failed_read_commits_no_mapping_request_or_sharing_change(db, api_client, two_tenant_world, monkeypatch, failure):
    name = _shared_world(db, api_client, monkeypatch, two_tenant_world)
    before = _state(db)
    postings = _change_everything(two_tenant_world, name)
    rows = _rows(600, "p3", "c")
    if failure == "unprovable":
        source = _Scripted(postings, [rows[:2], rows[:2]])
    else:
        source = FakeRecruitmentClient(postings, candidacies=rows, candidacies_down=failure == "down")
        source.fail_on_page = 2 if failure == "later_page" else None

    delivered = []
    body = consumer.run_reconcile(db, client=source, schedule_delivery=lambda f, e, **k: delivered.extend(e))
    assert body["outcome"] == "FAILED" and body["reasons"] == ["candidacies_unavailable"]
    assert _state(db) == before
    assert delivered == []


def test_an_over_budget_read_commits_no_mapping_request_or_sharing_change(db, api_client, two_tenant_world, monkeypatch):
    name = _shared_world(db, api_client, monkeypatch, two_tenant_world)
    before = _state(db)
    source = FakeRecruitmentClient(_change_everything(two_tenant_world, name), candidacies=_rows(3, "p3", "c"))
    delivered = []
    body = consumer.run_reconcile(db, client=source, budget_seconds=-1, schedule_delivery=lambda f, e, **k: delivered.extend(e))
    assert body["reasons"] == ["ReconcileBudgetExceeded"]
    assert _state(db) == before
    assert delivered == []


def test_a_complete_read_still_applies_mapping_changes(db, api_client, two_tenant_world, monkeypatch):
    name = _shared_world(db, api_client, monkeypatch, two_tenant_world)
    source = FakeRecruitmentClient(_change_everything(two_tenant_world, name), candidacies=_rows(3, "p3", "c"))
    delivered = []
    body = consumer.run_reconcile(db, client=source, schedule_delivery=lambda f, e, **k: delivered.extend(e))
    assert body["outcome"] == "SUCCEEDED"
    promotion = body["counts"]["promotion"]
    assert promotion["requests_access_withdrawn"] == 1 and promotion["requests_retired"] == 1
    assert promotion["talent_requests_created"] == 2
    db.expire_all()
    assert db.query(AuditOutbox).count() > 0
    db.expire_all()
    p3 = db.query(TalentRequest).filter_by(posting_external_id="p3").one()
    assert all(a.is_client_visible is False for a in p3.applications)
    p1 = db.query(TalentRequest).filter_by(posting_external_id="p1").one()
    assert all(a.is_client_visible is False for a in p1.applications)


REAL_SHAPE = [2090, 1839, 1188, 749, 707, 691, 686, 584, 547] + [149] * 12 + [148] * 12


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="volume timing needs PostgreSQL (postgres CI job)")
def test_real_verified_volume_first_load_and_rerun(db, two_tenant_world):
    name = two_tenant_world["abc"].name
    postings = [_posting(name, f"p{i:02}") for i in range(len(REAL_SHAPE))]
    rows = [r for i, n in enumerate(REAL_SHAPE) for r in _rows(n, posting=f"p{i:02}", prefix=f"{i:02}-")]
    source = FakeRecruitmentClient(postings, candidacies=rows)
    timings = []
    for _ in range(2):
        started = time.monotonic()
        body = consumer.run_reconcile(db, client=source, schedule_delivery=lambda *a, **k: None)
        timings.append(round(time.monotonic() - started, 1))
        assert body["outcome"] == "SUCCEEDED", body
    assert _count(db, Application) == len(rows)
    warnings.warn(f"reconcile volume rows={len(rows)} first_load_s={timings[0]} rerun_s={timings[1]}", stacklevel=1)


def test_promotion_lookups_do_not_grow_with_candidacies(db, two_tenant_world):
    """DEV's database is a network hop away, so per-candidacy queries cost
    the run its budget. Lookups must stay flat as the candidacy count grows."""
    from sqlalchemy import event

    from app.db.session import engine

    name = two_tenant_world["abc"].name

    def selects_for(count, prefix):
        postings = [_posting(name, f"{prefix}{i}") for i in range(3)]
        rows = [r for i in range(3) for r in _rows(count, posting=f"{prefix}{i}", prefix=f"{prefix}{i}-")]
        seen = []
        listener = lambda conn, cursor, stmt, *a: seen.append(stmt.lstrip().split()[0].upper())  # noqa: E731
        event.listen(engine, "before_cursor_execute", listener)
        try:
            body = consumer.run_reconcile(db, client=FakeRecruitmentClient(postings, candidacies=rows))
        finally:
            event.remove(engine, "before_cursor_execute", listener)
        assert body["outcome"] == "SUCCEEDED"
        assert body["counts"]["promotion"]["applications_created"] == 3 * count
        return seen.count("SELECT")

    small, large = selects_for(10, "s"), selects_for(400, "l")
    assert large - small < 20, (small, large)
