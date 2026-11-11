"""Client postings are all read eventually, and progress is reported honestly."""

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from app.models.posting import Posting
from app.models.recruitment_candidacy import RecruitmentCandidacy
from app.models.recruitment_candidate import RecruitmentCandidate
from app.models.sync_run import RecruitmentSyncRun, SyncStatus, SyncTriggerType
from app.services import lever_candidacy_sync_service as module
from app.services import recruitment_sync_service as sync_module
from app.services.lever_candidacy_sync_service import LeverCandidacySyncService
from app.services.recruitment_sync_service import RecruitmentSyncService
from tests.conftest import internal_headers

TOTAL = 70


def _opp(opp_id: str, contact: str | None = None):
    return SimpleNamespace(
        id=opp_id, contact_id=contact or f"c-{opp_id}", name="", email="", headline="", tags=[],
        sources=[], stage_id="", archived=False, archive_reason_id=None,
    )


class Lever:
    def __init__(self, per_posting=2, fail=(), interrupt_after=None):
        self.per_posting = per_posting
        self.fail = set(fail)
        self.interrupt_after = interrupt_after
        self.reads: list[str] = []

    def list_stages(self):
        return []

    def list_archive_reasons(self):
        return []

    def list_opportunities(self, posting_id=None, limit=None):
        if posting_id is None:
            return []
        if self.interrupt_after is not None and len(self.reads) >= self.interrupt_after:
            raise SystemExit("replica stopped")
        self.reads.append(posting_id)
        if posting_id in self.fail:
            raise RuntimeError("429 after retries")
        return [_opp(f"{posting_id}-{n}") for n in range(self.per_posting)]

    def list_applications(self, opportunity_id):
        return []


def _world(db, count=TOTAL):
    for n in range(count):
        db.add(Posting(lever_posting_id=f"p{n}", tags=json.dumps(["DTC - Acme"])))
    db.commit()


def _budget(monkeypatch, postings_per_run):
    """A clock that spends the budget after a fixed number of postings."""
    state = {"t": 0.0}
    step = module._DTC_READ_BUDGET_SECONDS / postings_per_run + 0.01

    def monotonic():
        state["t"] += step
        return state["t"]

    monkeypatch.setattr(module.time, "monotonic", monotonic)
    monkeypatch.setattr(module, "_GENERAL_READ_BUDGET_SECONDS", 1e12)


def _sync(db, monkeypatch, lever):
    monkeypatch.setattr(module, "get_lever_client", lambda: lever)
    return LeverCandidacySyncService(db).sync_opportunities(limit=200)


def _read_ids(db):
    db.expire_all()
    return {p.lever_posting_id for p in db.query(Posting).all() if p.dtc_last_read_at}


def test_more_than_63_postings_reach_completion_across_bounded_runs(db, monkeypatch):
    _world(db)
    _budget(monkeypatch, 20)
    lever = Lever()
    runs = []
    for _ in range(8):
        result = _sync(db, monkeypatch, lever)
        runs.append(result)
        if result["dtc_postings_remaining"] == 0:
            break
    assert runs[-1]["dtc_postings_remaining"] == 0
    assert len(runs) <= 5
    assert len(_read_ids(db)) == TOTAL
    assert runs[0]["dtc_postings_read"] + runs[0]["dtc_postings_deferred"] == TOTAL


def test_a_failing_posting_is_counted_and_cannot_starve_the_rest(db, monkeypatch):
    _world(db, 6)
    lever = Lever(fail={"p0", "p1"})
    result = _sync(db, monkeypatch, lever)
    assert (result["dtc_postings_read"], result["dtc_postings_failed"]) == (4, 2)
    assert result["dtc_postings_remaining"] == 2
    assert _read_ids(db) == {"p2", "p3", "p4", "p5"}


def test_repeated_failures_stop_early_and_later_runs_move_on(db, monkeypatch):
    _world(db, 8)
    lever = Lever(fail={"p0", "p1", "p2"})
    first = _sync(db, monkeypatch, lever)
    assert (first["dtc_postings_failed"], first["dtc_postings_deferred"]) == (3, 5)
    second = _sync(db, monkeypatch, lever)
    assert second["dtc_postings_read"] == 5
    assert _read_ids(db) == {"p3", "p4", "p5", "p6", "p7"}


def test_interrupted_run_keeps_progress_and_resumes_without_duplicates(db, monkeypatch):
    _world(db, 6)
    try:
        _sync(db, monkeypatch, Lever(interrupt_after=2))
    except SystemExit:
        db.rollback()
    assert len(_read_ids(db)) == 2
    before = db.query(RecruitmentCandidacy).count()
    assert before == 4
    lever = Lever()
    result = _sync(db, monkeypatch, lever)
    assert lever.reads[0] not in {"p0", "p1"}
    assert result["dtc_postings_remaining"] == 0 and len(_read_ids(db)) == 6
    _sync(db, monkeypatch, Lever())
    assert db.query(RecruitmentCandidacy).count() == 12
    assert db.query(RecruitmentCandidate).count() == 12


def test_general_budget_cannot_consume_the_client_posting_budget(db, monkeypatch):
    _world(db, 3)
    lever = Lever()
    lever_general = [_opp(f"g{n}") for n in range(5)]
    lever.list_opportunities = (
        lambda posting_id=None, limit=None, original=lever.list_opportunities:
        lever_general if posting_id is None else original(posting_id=posting_id)
    )
    state = {"t": 0.0}

    def monotonic():
        state["t"] += 100.0
        return state["t"]

    monkeypatch.setattr(module.time, "monotonic", monotonic)
    result = _sync(db, monkeypatch, lever)
    assert result["general_budget_exhausted"] is True
    assert result["dtc_postings_read"] == 3


def _execute(db, monkeypatch, opportunities):
    run, _ = RecruitmentSyncService(db).request_sync(
        trigger_type=SyncTriggerType.SCHEDULED, requested_by_application="test"
    )
    run_id = run.run_id
    monkeypatch.setattr(sync_module, "SessionLocal", lambda: db)
    monkeypatch.setattr(sync_module.LeverPostingSyncService, "sync_postings", lambda self: {"total": 10, "created": 1})
    monkeypatch.setattr(sync_module.LeverCandidacySyncService, "sync_opportunities", lambda self, limit: opportunities)
    monkeypatch.setattr(sync_module.platform_notify, "notify_module_role", lambda **kw: None)
    RecruitmentSyncService.execute_run(run_id)
    return RecruitmentSyncService(db).get(run_id)


def test_run_reports_failed_deferred_and_per_entity_counts(db, monkeypatch):
    run = _execute(db, monkeypatch, {
        "dtc_postings_read": 3, "dtc_postings_total": 7, "dtc_postings_failed": 1,
        "dtc_postings_deferred": 3, "dtc_postings_remaining": 4,
        "candidates_created": 5, "candidacies_created": 6,
    })
    assert run.status == SyncStatus.PARTIAL.value
    assert run.error_summary == "Incomplete: 3 of 7 client postings read; 1 failed, 3 deferred."
    detail = json.loads(run.detail)
    assert detail["client_postings"] == {
        "total": 7, "processed": 3, "current": 0, "failed": 1, "deferred": 3, "remaining": 4,
    }
    assert detail["candidates"]["created"] == 5 and detail["candidacies"]["created"] == 6
    assert detail["postings"]["total"] == 10


def test_general_budget_exhaustion_is_not_success(db, monkeypatch):
    run = _execute(db, monkeypatch, {"dtc_postings_read": 2, "dtc_postings_total": 2, "general_budget_exhausted": True})
    assert run.status == SyncStatus.PARTIAL.value


FINISHED = json.dumps({"general_budget_exhausted": False})


def _finished(db, status, age=timedelta(minutes=5), detail=FINISHED):
    done = datetime.now(UTC) - age
    db.add(RecruitmentSyncRun(
        run_id=f"r-{status}-{age.seconds}", provider="LEVER", trigger_type="SCHEDULED",
        requested_by_application="t", correlation_id="c", status=status.value,
        requested_at=done, completed_at=done, detail=detail,
    ))
    db.commit()


def _state(db):
    return RecruitmentSyncService(db).source_snapshot()["state"]


def _mark_all_read(db, age=timedelta(minutes=1)):
    for posting in db.query(Posting).all():
        posting.dtc_last_read_at = datetime.now(UTC) - age
    db.commit()


def test_snapshot_states(db):
    _world(db, 2)
    assert _state(db) == "NONE"
    _finished(db, SyncStatus.SUCCEEDED)
    assert _state(db) == "INCOMPLETE"
    _mark_all_read(db)
    assert _state(db) == "COMPLETE"
    _mark_all_read(db, module.SNAPSHOT_MAX_AGE + timedelta(minutes=1))
    assert _state(db) == "INCOMPLETE"


def test_snapshot_after_a_failed_or_old_run_is_not_complete(db):
    _world(db, 1)
    _mark_all_read(db)
    _finished(db, SyncStatus.SUCCEEDED, module.SNAPSHOT_MAX_AGE + timedelta(hours=2))
    assert _state(db) == "STALE"
    _finished(db, SyncStatus.FAILED)
    assert _state(db) == "FAILED"


def test_exhausted_general_read_or_missing_detail_is_not_complete(db):
    _world(db, 1)
    _mark_all_read(db)
    _finished(db, SyncStatus.PARTIAL, detail=json.dumps({"general_budget_exhausted": True}))
    assert _state(db) == "INCOMPLETE"
    db.query(RecruitmentSyncRun).delete()
    _finished(db, SyncStatus.SUCCEEDED, detail=None)
    assert _state(db) == "INCOMPLETE"


def test_no_client_postings_is_not_complete(db):
    _finished(db, SyncStatus.SUCCEEDED)
    assert _state(db) == "INCOMPLETE"


def test_a_prompt_rerun_skips_current_postings_and_is_not_partial(db, monkeypatch):
    _world(db, 4)
    _sync(db, monkeypatch, Lever())
    again = Lever()
    result = _sync(db, monkeypatch, again)
    assert again.reads == []
    assert (result["dtc_postings_read"], result["dtc_postings_current"], result["dtc_postings_remaining"]) == (0, 4, 0)


class _Clock(datetime):
    now_value = datetime(2026, 1, 1, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls.now_value


def test_slow_throughput_converges_before_checkpoints_expire(db, monkeypatch):
    """Ten postings per 6-hourly run: all 70 are current together by the 7th run."""
    _world(db)
    _budget(monkeypatch, 10)
    monkeypatch.setattr(module, "datetime", _Clock)
    lever = Lever()
    remaining = []
    for run in range(8):
        _Clock.now_value = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=6 * run)
        remaining.append(_sync(db, monkeypatch, lever)["dtc_postings_remaining"])
    assert 0 in remaining[:7]
    assert remaining[:6] == sorted(remaining[:6], reverse=True)


def test_a_new_client_posting_invalidates_a_complete_snapshot_until_read(db, monkeypatch):
    _world(db, 2)
    _mark_all_read(db)
    _finished(db, SyncStatus.SUCCEEDED)
    assert _state(db) == "COMPLETE"
    db.add(Posting(lever_posting_id="new", tags=json.dumps(["DTC - Newco"])))
    db.commit()
    assert _state(db) == "INCOMPLETE"
    lever = Lever()
    _sync(db, monkeypatch, lever)
    assert lever.reads == ["new"]
    assert _state(db) == "COMPLETE"


def test_growing_postings_with_slow_throughput_and_a_bad_posting_still_converge(db, monkeypatch):
    _world(db, 40)
    _budget(monkeypatch, 15)
    monkeypatch.setattr(module, "datetime", _Clock)
    lever = Lever(fail={"p3"})
    unread = []
    for run in range(8):
        _Clock.now_value = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=6 * run)
        if run in (2, 3):
            db.add_all([Posting(lever_posting_id=f"g{run}{n}", tags=json.dumps(["DTC - Acme"])) for n in range(5)])
            db.commit()
        if run == 6:
            lever.fail.clear()
        unread.append(_sync(db, monkeypatch, lever)["dtc_postings_remaining"])
    assert unread[6] <= 1 and unread[7] == 0


def test_categories_add_up(db, monkeypatch):
    _world(db, 8)
    _mark_all_read(db, timedelta(hours=1))
    for posting in db.query(Posting).filter(Posting.lever_posting_id.in_(["p0", "p1", "p2", "p3", "p4"])).all():
        posting.dtc_last_read_at = None
    db.commit()
    result = _sync(db, monkeypatch, Lever(fail={"p0", "p1", "p2"}))
    assert result["dtc_postings_current"] == 3 and result["dtc_postings_failed"] == 3
    assert result["dtc_postings_deferred"] == 2 and result["dtc_postings_read"] == 0
    assert result["dtc_postings_remaining"] == 5


def test_a_crash_during_a_posting_cannot_block_the_queue(db, monkeypatch):
    _world(db, 3)
    try:
        _sync(db, monkeypatch, Lever(interrupt_after=0))
    except SystemExit:
        db.rollback()
    lever = Lever()
    _sync(db, monkeypatch, lever)
    assert lever.reads[0] != "p0" and lever.reads[-1] == "p0"


def test_job_script_reads_the_real_status_route(db, api_client, monkeypatch):
    runner = _runner()
    run = RecruitmentSyncRun(
        run_id="real", provider="LEVER", trigger_type="SCHEDULED", requested_by_application="t",
        correlation_id="c", status=SyncStatus.PARTIAL.value,
    )
    db.add(run)
    db.commit()
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    monkeypatch.setattr(sync_module.RecruitmentSyncService, "execute_run", staticmethod(lambda run_id: None))

    def call(method, path):
        if method == "POST":
            return {"run_id": "real"}
        return api_client.get(f"/api/recruitment{path}", headers=internal_headers()).json()

    monkeypatch.setattr(runner, "call", call)
    assert runner.main() == 0


def test_job_reports_bounded_failures(monkeypatch, capsys):
    runner = _runner()
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)

    def refused(method, path):
        raise runner.urllib.error.URLError("refused")

    monkeypatch.setattr(runner, "call", refused)
    assert runner.main() == 1
    assert "sync_outcome=NOT_STARTED" in capsys.readouterr().err

    def status_down(method, path):
        if method == "POST":
            return {"run_id": "r"}
        raise TimeoutError

    monkeypatch.setattr(runner, "call", status_down)
    assert runner.main() == 1
    assert "sync_outcome=UNKNOWN" in capsys.readouterr().err


def _runner():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_scheduled_sync.py"
    spec = importlib.util.spec_from_file_location("run_scheduled_sync", path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def _drive(monkeypatch, statuses):
    runner = _runner()
    answers = iter(statuses)
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)

    def call(method, path):
        return {"run_id": "r1"} if method == "POST" else {"run": {"status": next(answers)}}

    monkeypatch.setattr(runner, "call", call)
    return runner.main()


def test_job_waits_for_the_result_and_reports_failure(monkeypatch):
    assert _drive(monkeypatch, ["RUNNING", "RUNNING", "SUCCEEDED"]) == 0
    assert _drive(monkeypatch, ["RUNNING", "PARTIAL"]) == 0
    assert _drive(monkeypatch, ["FAILED"]) == 1
