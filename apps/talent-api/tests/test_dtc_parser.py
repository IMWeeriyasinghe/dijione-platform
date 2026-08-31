"""Governed DTC posting-tag parser (Recruitment Source provider fact).

Only the exact "DTC - <Client Name>" convention is eligible. Every
ambiguous/malformed case is reported so the reconciler can fail closed.
"""

import pytest

from app.recruitment_source.dtc import DtcParseStatus, parse_dtc


@pytest.mark.parametrize(
    "tags,expected_name",
    [
        (["DTC - Agent Maestro"], "Agent Maestro"),
        (["DTC - Crofti"], "Crofti"),
        (["  DTC - Agent Maestro  "], "Agent Maestro"),
        (["dtc - Agent Maestro"], "Agent Maestro"),
        (["DTC-Agent Maestro"], "Agent Maestro"),
        (["DTC   -   Agent Maestro"], "Agent Maestro"),
        (["Priority", "DTC - Crofti", "Remote"], "Crofti"),  # non-DTC tags ignored
        (["DTC - O'Brien & Sons"], "O'Brien & Sons"),  # internal punctuation/space preserved
    ],
)
def test_valid_dtc_tag_parses(tags, expected_name):
    r = parse_dtc(tags)
    assert r.status is DtcParseStatus.OK
    assert r.client_name == expected_name
    assert r.raw_tag is not None


@pytest.mark.parametrize("tags", [None, [], ["Priority"], ["Remote", "Full Time"], ["DTContractor"]])
def test_no_dtc_tag(tags):
    assert parse_dtc(tags).status is DtcParseStatus.NO_TAG


@pytest.mark.parametrize("tags", [["DTC"], ["DTC -"], ["DTC -    "], ["  dtc  -  "]])
def test_malformed_dtc_tag(tags):
    r = parse_dtc(tags)
    assert r.status is DtcParseStatus.MALFORMED
    assert r.client_name is None


def test_multiple_dtc_tags_is_ambiguous():
    r = parse_dtc(["DTC - Crofti", "DTC - Agent Maestro"])
    assert r.status is DtcParseStatus.MULTIPLE
    assert set(r.raw_tags) == {"DTC - Crofti", "DTC - Agent Maestro"}
    assert r.client_name is None


def test_non_string_tags_are_ignored():
    assert parse_dtc([None, 123, {"x": 1}, "DTC - Crofti"]).client_name == "Crofti"  # type: ignore[list-item]
