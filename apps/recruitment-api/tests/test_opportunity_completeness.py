"""The opportunity cap must not leave client-tagged postings incomplete."""

import json
from types import SimpleNamespace

from app.models.posting import Posting
from app.models.recruitment_candidacy import RecruitmentCandidacy
from app.services import lever_candidacy_sync_service as module
from app.services.lever_candidacy_sync_service import LeverCandidacySyncService


def _opp(opp_id: str):
    return SimpleNamespace(
        id=opp_id, contact_id=f"contact-{opp_id}", name="", email="", headline="", tags=[],
        sources=[], stage_id="", archived=False, archive_reason_id=None,
    )


class FakeLever:
    """Newest-first opportunities. ``by_posting`` is what the filter returns."""

    def __init__(self, recent, by_posting):
        self.recent = recent
        self.by_posting = by_posting
        self.application_calls = 0
        self.filter_calls = []

    def list_stages(self):
        return []

    def list_archive_reasons(self):
        return []

    def list_opportunities(self, posting_id=None, limit=None):
        if posting_id is None:
            return self.recent[:limit]
        self.filter_calls.append(posting_id)
        return self.by_posting.get(posting_id, [])

    def list_applications(self, opportunity_id):
        self.application_calls += 1
        return [SimpleNamespace(posting_id="untagged")]


def _posting(db, lever_id: str, tags: list[str]) -> Posting:
    posting = Posting(lever_posting_id=lever_id, tags=json.dumps(tags))
    db.add(posting)
    db.flush()
    return posting


def _run(db, monkeypatch, lever, limit=2):
    monkeypatch.setattr(module, "get_lever_client", lambda: lever)
    return LeverCandidacySyncService(db).sync_opportunities(limit=limit)


def test_opportunities_beyond_the_cap_are_read_for_tagged_postings(db, monkeypatch):
    tagged = _posting(db, "tagged", ["DTC - Acme"])
    _posting(db, "untagged", [])
    lever = FakeLever(
        recent=[_opp("new-1"), _opp("new-2"), _opp("beyond-cap")],
        by_posting={"tagged": [_opp("old-1"), _opp("old-2")]},
    )

    result = _run(db, monkeypatch, lever)

    assert result["opportunity_limit_reached"] is True
    assert result["dtc_opportunities_seen"] == 2
    assert lever.filter_calls == ["tagged"]
    rows = db.query(RecruitmentCandidacy).filter_by(posting_id=tagged.id).all()
    assert {r.lever_opportunity_id for r in rows} == {"old-1", "old-2"}
    assert lever.application_calls == 2  # none for the filtered reads


def test_opportunity_in_both_reads_is_processed_once_and_rerun_is_stable(db, monkeypatch):
    _posting(db, "tagged", ["DTC - Acme"])
    _posting(db, "untagged", [])
    shared = _opp("both")
    lever = FakeLever(recent=[shared], by_posting={"tagged": [shared, _opp("only-filtered")]})

    first = _run(db, monkeypatch, lever)
    second = _run(db, monkeypatch, lever)

    assert first["opportunity_limit_reached"] is False
    assert first["dtc_opportunities_seen"] == 1
    assert first["candidacies_created"] == 2
    assert second["candidacies_created"] == 0
    assert db.query(RecruitmentCandidacy).count() == 2


def test_untagged_postings_are_not_read_in_full(db, monkeypatch):
    _posting(db, "untagged", ["Engineering"])
    lever = FakeLever(recent=[], by_posting={"untagged": [_opp("ignored")]})

    result = _run(db, monkeypatch, lever)

    assert lever.filter_calls == []
    assert result["dtc_postings_read"] == 0


def test_posting_reads_stop_at_the_budget_and_report_it(db, monkeypatch, caplog):
    _posting(db, "tagged-a", ["DTC - Acme"])
    _posting(db, "tagged-b", ["DTC - Beta"])
    lever = FakeLever(recent=[], by_posting={})
    clock = iter([0.0, 1.0, module._DTC_READ_BUDGET_SECONDS + 1])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(clock))

    with caplog.at_level("WARNING"):
        result = _run(db, monkeypatch, lever)

    assert (result["dtc_postings_read"], result["dtc_postings_total"]) == (1, 2)
    assert "incomplete" in caplog.text
