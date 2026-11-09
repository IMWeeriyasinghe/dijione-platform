"""Scheduled reconcile: real outcomes, cold-start handling, single-flight and
transaction safety on POST /api/talent/internal/recruitment/reconcile."""

import threading

import httpx
import pytest

from app.db.session import SessionLocal, engine
from app.models.application import Application
from app.models.candidate import Candidate
from app.models.recruitment_posting_ref import RecruitmentPostingRef
from app.models.talent_request import TalentRequest
from app.services import recruitment_consumer_service as consumer
from tests.conftest import FakeRecruitmentClient, recruitment_candidacy_dto, recruitment_posting_dto

URL = "/api/talent/internal/recruitment/reconcile"
HEADERS = {"X-Internal-Token": "test-only-internal-secret"}


def _source(world, **kwargs):
    name = world["abc"].name
    return FakeRecruitmentClient(
        [recruitment_posting_dto(
            "p1", title="Engineer", dtc_status="OK", dtc_client_name=name, dtc_raw_tag=f"DTC - {name}",
        )],
        candidacies=kwargs.pop("candidacies", [recruitment_candidacy_dto(
            "opp-1", posting_external_id="p1", candidate_external_id="contact-1",
        )]),
        **kwargs,
    )


def _use(monkeypatch, client):
    monkeypatch.setattr("app.api.routes.recruitment.get_recruitment_batch_client", lambda: client)


def _counts(db):
    db.expire_all()
    return (
        db.query(RecruitmentPostingRef).count(), db.query(TalentRequest).count(),
        db.query(Candidate).count(), db.query(Application).count(),
    )


def test_requires_internal_token(api_client, db):
    assert api_client.post(URL).status_code in (401, 403)


def test_success_is_200_and_fully_refreshed(api_client, db, two_tenant_world, monkeypatch):
    _use(monkeypatch, _source(two_tenant_world))
    resp = api_client.post(URL, headers=HEADERS)
    body = resp.json()
    assert resp.status_code == 200
    assert body["outcome"] == "SUCCEEDED" and body["fully_refreshed"] is True
    assert body["counts"]["promotion"]["talent_requests_created"] == 1
    assert _counts(db) == (1, 1, 1, 1)


def test_response_contains_aggregates_only(api_client, db, two_tenant_world, monkeypatch):
    _use(monkeypatch, _source(two_tenant_world))
    text = api_client.post(URL, headers=HEADERS).text
    assert "contact-1" not in text and "Engineer" not in text and "@" not in text


def test_source_down_is_failed_not_success(api_client, db, two_tenant_world, monkeypatch):
    _use(monkeypatch, FakeRecruitmentClient(down=True))
    resp = api_client.post(URL, headers=HEADERS)
    body = resp.json()
    assert resp.status_code == 503
    assert body["outcome"] == "FAILED" and body["fully_refreshed"] is False
    assert body["reasons"] == ["source_unavailable"]
    assert _counts(db) == (0, 0, 0, 0)


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"candidacies_down": True}, "candidacies_unavailable"),
        ({"candidacies": [
            recruitment_candidacy_dto(f"o{i}", posting_external_id="p1", candidate_external_id=f"c{i}")
            for i in range(500)
        ]}, "candidacy_limit_hit"),
    ],
)
def test_partial_is_non_2xx_and_never_fully_refreshed(
    api_client, db, two_tenant_world, monkeypatch, kwargs, reason
):
    _use(monkeypatch, _source(two_tenant_world, **kwargs))
    resp = api_client.post(URL, headers=HEADERS)
    body = resp.json()
    assert resp.status_code == 503
    assert body["outcome"] == "PARTIAL" and body["fully_refreshed"] is False
    assert body["reasons"] == [reason]


def test_no_postings_is_partial(api_client, db, two_tenant_world, monkeypatch):
    _use(monkeypatch, FakeRecruitmentClient([]))
    body = api_client.post(URL, headers=HEADERS).json()
    assert body["outcome"] == "PARTIAL" and body["reasons"] == ["no_postings"]


def test_retry_completes_partial_without_duplicates(api_client, db, two_tenant_world, monkeypatch):
    _use(monkeypatch, _source(two_tenant_world, candidacies_down=True))
    api_client.post(URL, headers=HEADERS)
    assert _counts(db) == (1, 1, 0, 0)

    _use(monkeypatch, _source(two_tenant_world))
    assert api_client.post(URL, headers=HEADERS).status_code == 200
    assert api_client.post(URL, headers=HEADERS).status_code == 200
    assert _counts(db) == (1, 1, 1, 1)


def _cold_source(world, startup_seconds):
    """httpx.request stand-in: a caller that gives up before the replica is
    ready times out, as when the Container Apps proxy holds a cold request."""
    name = world["abc"].name
    posting = recruitment_posting_dto(
        "p1", dtc_status="OK", dtc_client_name=name, dtc_raw_tag=f"DTC - {name}"
    )

    def fake(method, url, timeout=None, **kwargs):
        if timeout < startup_seconds:
            raise httpx.ReadTimeout("cold start")
        body = [posting] if url.endswith("/postings") else []
        if url.endswith("/freshness"):
            body = {"source_snapshot": {"state": "COMPLETE"}}
        return httpx.Response(200, json=body, request=httpx.Request(method, url))

    return fake


def test_cold_start_defeats_interactive_timeout(db, two_tenant_world, monkeypatch):
    monkeypatch.setattr(httpx, "request", _cold_source(two_tenant_world, 47))
    report = consumer.run_reconcile(db, client=consumer.get_recruitment_client())
    assert report["outcome"] == "FAILED" and report["reasons"] == ["source_unavailable"]


def test_batch_timeout_survives_worst_observed_cold_start(api_client, db, two_tenant_world, monkeypatch):
    monkeypatch.setattr(httpx, "request", _cold_source(two_tenant_world, 47))
    resp = api_client.post(URL, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["outcome"] == "SUCCEEDED"


def test_timeouts_and_budget_fit_hosting_limits():
    assert consumer.get_recruitment_client()._timeout == 5.0
    assert consumer.get_recruitment_batch_client()._timeout == 90.0
    assert 2 * consumer.BATCH_SOURCE_TIMEOUT_SECONDS < consumer.RECONCILE_BUDGET_SECONDS < 240


def test_concurrent_run_is_skipped(api_client, db, two_tenant_world, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    source = _source(two_tenant_world)
    original = source.list_postings

    def blocking(**kwargs):
        entered.set()
        assert release.wait(10)
        return original(**kwargs)

    source.list_postings = blocking
    reports = {}

    def first():
        session = SessionLocal()
        try:
            reports["first"] = consumer.run_reconcile(session, client=source)
        finally:
            session.close()

    thread = threading.Thread(target=first)
    thread.start()
    assert entered.wait(10)
    _use(monkeypatch, _source(two_tenant_world))
    resp = api_client.post(URL, headers=HEADERS)
    release.set()
    thread.join(10)

    assert resp.status_code == 409
    assert resp.json()["outcome"] == "SKIPPED" and resp.json()["reasons"] == ["already_running"]
    assert reports["first"]["outcome"] == "SUCCEEDED"
    assert _counts(db) == (1, 1, 1, 1)


class _PgSession:
    """Records guard behaviour against a PostgreSQL-dialect session."""

    def __init__(self, granted):
        self.granted, self.sql, self.rollbacks = granted, [], 0

    def get_bind(self):
        class Bind:
            class dialect:  # noqa: N801
                name = "postgresql"

        return Bind

    def execute(self, statement, params=None):
        self.sql.append((str(statement), params))
        granted = self.granted

        class Result:
            scalar = staticmethod(lambda: granted)

        return Result

    def rollback(self):
        self.rollbacks += 1


@pytest.mark.parametrize("granted", [True, False])
def test_postgres_guard_uses_transaction_advisory_lock(granted):
    session = _PgSession(granted)
    with consumer.reconcile_guard(session) as acquired:
        assert acquired is granted
        assert session.rollbacks == 0
    assert "pg_try_advisory_xact_lock" in session.sql[0][0]
    assert any("statement_timeout" in sql for sql, _ in session.sql) is granted
    assert any("lock_timeout" in sql for sql, _ in session.sql) is granted
    assert session.rollbacks == 1


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="needs PostgreSQL (postgres CI job)")
def test_postgres_lock_excludes_second_session():
    one, two = SessionLocal(), SessionLocal()
    try:
        with consumer.reconcile_guard(one) as first:
            assert first is True
            with consumer.reconcile_guard(two) as second:
                assert second is False
        with consumer.reconcile_guard(two) as after_release:
            assert after_release is True
    finally:
        one.close()
        two.close()


def test_exception_rolls_back_everything_and_hides_detail(api_client, db, two_tenant_world, monkeypatch):
    _use(monkeypatch, _source(two_tenant_world))

    def boom(self, *, candidacies, candidacy_limit_hit=False):
        self.db.flush()
        raise RuntimeError("secret candidate detail")

    monkeypatch.setattr(consumer.VerifiedPostingPromotionReconciler, "reconcile", boom)
    resp = api_client.post(URL, headers=HEADERS)
    assert resp.status_code == 503
    assert resp.json()["outcome"] == "FAILED" and resp.json()["reasons"] == ["RuntimeError"]
    assert "secret candidate detail" not in resp.text
    assert _counts(db) == (0, 0, 0, 0)


def test_commit_failure_is_failed(db, two_tenant_world, monkeypatch):
    client = _source(two_tenant_world)
    session = SessionLocal()

    def failing_commit():
        raise RuntimeError("commit")

    try:
        monkeypatch.setattr(session, "commit", failing_commit)
        report = consumer.run_reconcile(session, client=client)
    finally:
        session.close()
    assert report["outcome"] == "FAILED"
    assert _counts(db) == (0, 0, 0, 0)


def test_budget_overrun_rolls_back(api_client, db, two_tenant_world, monkeypatch):
    _use(monkeypatch, _source(two_tenant_world))
    monkeypatch.setattr(consumer, "RECONCILE_BUDGET_SECONDS", -1.0)
    body = api_client.post(URL, headers=HEADERS).json()
    assert body["outcome"] == "FAILED" and body["reasons"] == ["ReconcileBudgetExceeded"]
    assert _counts(db) == (0, 0, 0, 0)


def test_retry_after_failure_succeeds_without_duplicates(api_client, db, two_tenant_world, monkeypatch):
    _use(monkeypatch, FakeRecruitmentClient(down=True))
    api_client.post(URL, headers=HEADERS)
    _use(monkeypatch, _source(two_tenant_world))
    assert api_client.post(URL, headers=HEADERS).status_code == 200
    assert _counts(db) == (1, 1, 1, 1)


def test_lock_is_released_after_failure(api_client, db, two_tenant_world, monkeypatch):
    _use(monkeypatch, FakeRecruitmentClient(down=True))
    api_client.post(URL, headers=HEADERS)
    assert not consumer._local_reconcile_lock.locked()


def test_side_effects_sent_only_after_commit(api_client, db, two_tenant_world, monkeypatch, platform_calls):
    _use(monkeypatch, _source(two_tenant_world))
    order = []
    real_commit = consumer.Session.commit
    audit_seen_at_commit = []

    def spying_commit(self):
        audit_seen_at_commit.append(len(platform_calls["audit_events"]))
        order.append("commit")
        return real_commit(self)

    monkeypatch.setattr(consumer.Session, "commit", spying_commit)
    assert api_client.post(URL, headers=HEADERS).status_code == 200
    assert audit_seen_at_commit == [0]
    assert platform_calls["audit_events"]


def test_rollback_sends_no_side_effects(api_client, db, two_tenant_world, monkeypatch, platform_calls):
    _use(monkeypatch, _source(two_tenant_world))
    monkeypatch.setattr(consumer, "RECONCILE_BUDGET_SECONDS", -1.0)
    api_client.post(URL, headers=HEADERS)
    assert platform_calls["audit_events"] == []
    assert platform_calls["broadcasts"] == []


def test_retry_does_not_duplicate_audit(api_client, db, two_tenant_world, monkeypatch, platform_calls):
    _use(monkeypatch, _source(two_tenant_world))
    api_client.post(URL, headers=HEADERS)
    first = len(platform_calls["audit_events"])
    api_client.post(URL, headers=HEADERS)
    assert first > 0 and len(platform_calls["audit_events"]) == first


def test_persisting_conflict_notifies_once(api_client, db, two_tenant_world, monkeypatch, platform_calls):
    from app.repositories.posting_client_mapping_repo import PostingClientMappingRepository

    _use(monkeypatch, _source(two_tenant_world))
    api_client.post(URL, headers=HEADERS)
    mapping = PostingClientMappingRepository(db).get_for_posting("p1")
    mapping.source = "MANUAL"
    mapping.client_id = two_tenant_world["xyz"].id
    db.commit()

    api_client.post(URL, headers=HEADERS)
    api_client.post(URL, headers=HEADERS)
    assert len(platform_calls["broadcasts"]) == 1


def test_partial_never_shares_or_withdraws(api_client, db, two_tenant_world, monkeypatch):
    _use(monkeypatch, _source(two_tenant_world))
    api_client.post(URL, headers=HEADERS)
    db.expire_all()
    application = db.query(Application).one()
    application.is_client_visible = True
    db.commit()

    _use(monkeypatch, _source(two_tenant_world, candidacies_down=True))
    assert api_client.post(URL, headers=HEADERS).json()["outcome"] == "PARTIAL"
    _use(monkeypatch, FakeRecruitmentClient([]))
    assert api_client.post(URL, headers=HEADERS).json()["reasons"] == ["no_postings"]
    assert _counts(db) == (1, 1, 1, 1)
    assert db.query(Application).one().is_client_visible is True


def test_partial_new_applications_stay_unshared(api_client, db, two_tenant_world, monkeypatch):
    rows = [
        recruitment_candidacy_dto(f"o{i}", posting_external_id="p1", candidate_external_id=f"c{i}")
        for i in range(500)
    ]
    _use(monkeypatch, _source(two_tenant_world, candidacies=rows))
    assert api_client.post(URL, headers=HEADERS).json()["outcome"] == "PARTIAL"
    db.expire_all()
    assert db.query(Application).filter(Application.is_client_visible.is_(True)).count() == 0


def test_delivery_is_time_limited_and_survives_errors():
    from app.services.side_effects import deliver_side_effects

    sent = []

    def bad():
        raise RuntimeError("platform down")

    deliver_side_effects([bad, lambda: sent.append(1)], limit_seconds=5)
    assert sent == [1]
    deliver_side_effects([lambda: sent.append(2)], limit_seconds=-1)
    assert sent == [1]
