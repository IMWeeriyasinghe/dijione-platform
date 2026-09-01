"""LiveLeverClient._to_posting mapping — pure function, no network call.

Real bug found by a live-data idempotency check (Architecture Completion
Plan real-data validation, 2026-09-01): a second sync run against the real
Lever tenant failed with `IntegrityError: NOT NULL constraint failed:
postings.team`, because Lever's real API returns some postings with an
explicit JSON `null` for a categories field the mock fixture data never
exercised. `.get(key, "")` only substitutes the default when `key` is
*absent* from the dict — a present key mapped to `null` passes straight
through as `None`, later violating the NOT NULL column. These tests pin
the fix (`.get(key) or ""`) against every affected field so this class of
bug can't silently regress.
"""

from app.integrations.lever.live_client import LiveLeverClient

_BASE_RAW_POSTING = {
    "id": "posting-external-id",
    "text": "Some Role",
    "state": "published",
    "categories": {"team": "Engineering", "department": "IT", "location": "Colombo"},
    "owner": "user-owner-1",
    "hiringManager": "user-hm-1",
    "confidentiality": "non-confidential",
    "tags": ["DTC - Some Client"],
    "archived": False,
    "createdAt": None,
    "updatedAt": None,
}


def test_to_posting_maps_a_fully_populated_payload():
    posting = LiveLeverClient._to_posting(_BASE_RAW_POSTING)
    assert posting.team == "Engineering"
    assert posting.department == "IT"
    assert posting.location == "Colombo"
    assert posting.owner_user_id == "user-owner-1"
    assert posting.state == "published"
    assert posting.confidentiality == "non-confidential"
    assert posting.text == "Some Role"


def test_to_posting_normalizes_explicit_null_team_to_empty_string():
    """The exact real-world shape that broke the second sync run: `team`
    present in `categories` but explicitly `null`, not merely absent."""
    raw = {**_BASE_RAW_POSTING, "categories": {**_BASE_RAW_POSTING["categories"], "team": None}}
    posting = LiveLeverClient._to_posting(raw)
    assert posting.team == ""


def test_to_posting_normalizes_every_not_null_field_when_explicitly_null():
    raw = {
        **_BASE_RAW_POSTING,
        "text": None,
        "state": None,
        "owner": None,
        "confidentiality": None,
        "categories": {"team": None, "department": None, "location": None},
    }
    posting = LiveLeverClient._to_posting(raw)
    assert posting.text == ""
    assert posting.state == ""
    assert posting.owner_user_id == ""
    assert posting.confidentiality == ""
    assert posting.team == ""
    assert posting.department == ""
    assert posting.location == ""


def test_to_posting_normalizes_missing_keys_the_same_as_explicit_null():
    """Both failure shapes (absent key vs. present-but-null) must converge
    on the same "" result — not just the absent-key case `.get(key, "")`
    already handled correctly."""
    raw = {
        "id": "posting-external-id",
        "createdAt": None,
        "updatedAt": None,
        "archived": False,
    }
    posting = LiveLeverClient._to_posting(raw)
    assert posting.text == ""
    assert posting.state == ""
    assert posting.team == ""
    assert posting.department == ""
    assert posting.location == ""
    assert posting.owner_user_id == ""
    assert posting.hiring_manager_user_id == ""
    assert posting.confidentiality == ""


def test_to_posting_missing_categories_key_entirely_does_not_raise():
    raw = {k: v for k, v in _BASE_RAW_POSTING.items() if k != "categories"}
    posting = LiveLeverClient._to_posting(raw)
    assert posting.team == ""
    assert posting.department == ""
    assert posting.location == ""


def test_to_posting_null_categories_object_itself_does_not_raise():
    raw = {**_BASE_RAW_POSTING, "categories": None}
    posting = LiveLeverClient._to_posting(raw)
    assert posting.team == ""
