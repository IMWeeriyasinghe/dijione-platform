"""Unit tests for the central eligibility rule
(``app/services/eligibility_service.py``)."""

from __future__ import annotations

from datetime import date

from app.core.constants import EligibilityReason
from app.services.eligibility_service import compute_eligibility


def _kwargs(**overrides):
    defaults = dict(
        employment_status="Active",
        hire_date=date(2019, 1, 1),
        termination_date=None,
        birth_month=6,
        birth_day=15,
        occurrence_date=date(2026, 6, 15),
    )
    defaults.update(overrides)
    return defaults


def test_active_and_already_hired_is_eligible():
    eligible, reason = compute_eligibility(**_kwargs())
    assert eligible is True
    assert reason == EligibilityReason.ELIGIBLE


def test_hire_date_equal_to_occurrence_is_eligible():
    eligible, reason = compute_eligibility(**_kwargs(hire_date=date(2026, 6, 15)))
    assert eligible is True
    assert reason == EligibilityReason.ELIGIBLE


def test_hire_date_after_occurrence_is_future_starter():
    """Hired Oct 1, birthday Sept 28 this year -> not eligible this cycle."""
    eligible, reason = compute_eligibility(
        **_kwargs(hire_date=date(2026, 10, 1), occurrence_date=date(2026, 9, 28))
    )
    assert eligible is False
    assert reason == EligibilityReason.FUTURE_STARTER


def test_inactive_employee_is_ineligible():
    eligible, reason = compute_eligibility(**_kwargs(employment_status="Inactive"))
    assert eligible is False
    assert reason == EligibilityReason.INACTIVE_EMPLOYEE


def test_terminated_before_birthday_is_ineligible():
    eligible, reason = compute_eligibility(
        **_kwargs(employment_status="Inactive", termination_date=date(2026, 5, 1))
    )
    assert eligible is False
    # INACTIVE_EMPLOYEE wins first (status check comes before termination-date
    # check) — both reasons would be true here, and status is checked first.
    assert reason == EligibilityReason.INACTIVE_EMPLOYEE


def test_terminated_before_birthday_with_active_status_stale_data_is_employment_ended():
    """Edge case: BambooHR status hasn't caught up (still shows Active) but
    a termination date before the birthday occurrence already exists —
    must still be excluded, not silently treated as eligible."""
    eligible, reason = compute_eligibility(
        **_kwargs(employment_status="Active", termination_date=date(2026, 5, 1))
    )
    assert eligible is False
    assert reason == EligibilityReason.EMPLOYMENT_ENDED


def test_termination_after_birthday_still_eligible():
    eligible, reason = compute_eligibility(
        **_kwargs(termination_date=date(2026, 12, 31))
    )
    assert eligible is True
    assert reason == EligibilityReason.ELIGIBLE


def test_missing_birthday_is_ineligible():
    eligible, reason = compute_eligibility(**_kwargs(birth_month=None, birth_day=None))
    assert eligible is False
    assert reason == EligibilityReason.MISSING_BIRTHDAY


def test_missing_hire_date_is_ineligible():
    eligible, reason = compute_eligibility(**_kwargs(hire_date=None))
    assert eligible is False
    assert reason == EligibilityReason.MISSING_HIRE_DATE


def test_invalid_birth_month_is_invalid_employee_data():
    eligible, reason = compute_eligibility(**_kwargs(birth_month=13, birth_day=1))
    assert eligible is False
    assert reason == EligibilityReason.INVALID_EMPLOYEE_DATA
