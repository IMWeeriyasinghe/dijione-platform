"""Central birthday-cake-order eligibility rule — the single place this
business rule is evaluated. Never re-derived in the frontend; the backend
result (``eligible`` + ``eligibility_reason``) is what both the directory
view and the detection scan's order-creation gate rely on.

Rule (fixed order — first failing check wins, matching
``EligibilityReason``'s intent as a diagnostic, not just a boolean):

1. valid birthday exists (else MISSING_BIRTHDAY)
2. status is Active (else INACTIVE_EMPLOYEE)
3. hire/start date is known (else MISSING_HIRE_DATE)
4. hire/start date <= this birthday occurrence date (else FUTURE_STARTER)
   -- confirmed live against the real BambooHR tenant that an employee CAN
   show status=Active before their hire date (9 such records observed
   2026-08-14), so this check cannot be skipped just because status=Active.
5. no termination date before this birthday occurrence (else
   EMPLOYMENT_ENDED)

Anything that doesn't fit the above (e.g. a malformed date that still
reached this function) falls through to INVALID_EMPLOYEE_DATA.
"""

from __future__ import annotations

from datetime import date

from app.core.constants import EligibilityReason


def compute_eligibility(
    *,
    employment_status: str,
    hire_date: date | None,
    termination_date: date | None,
    birth_month: int | None,
    birth_day: int | None,
    occurrence_date: date,
) -> tuple[bool, EligibilityReason]:
    if birth_month is None or birth_day is None:
        return False, EligibilityReason.MISSING_BIRTHDAY

    if not (1 <= birth_month <= 12 and 1 <= birth_day <= 31):
        return False, EligibilityReason.INVALID_EMPLOYEE_DATA

    if employment_status != "Active":
        return False, EligibilityReason.INACTIVE_EMPLOYEE

    if hire_date is None:
        return False, EligibilityReason.MISSING_HIRE_DATE

    if hire_date > occurrence_date:
        return False, EligibilityReason.FUTURE_STARTER

    if termination_date is not None and termination_date < occurrence_date:
        return False, EligibilityReason.EMPLOYMENT_ENDED

    return True, EligibilityReason.ELIGIBLE
