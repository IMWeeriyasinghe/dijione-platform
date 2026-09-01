"""Maps Lever's actual pipeline stage names and archive reasons into
DijiOne's fixed canonical concepts (CLAUDE.md §30). Rewritten against the
real 14-stage Dijital Team Lever pipeline, confirmed by live read-only
tenant discovery — nothing else in the app should need to change, since
routes/UI only ever see CanonicalStage/ApplicationStatus values.

Several entries below are PROPOSED DEFAULTS, not confirmed final business
labels — each is commented where genuinely ambiguous. Do not treat these
as settled without a business decision.
"""

from app.core.constants import ApplicationStatus, CanonicalStage

LEVER_STAGE_MAP: dict[str, CanonicalStage] = {
    # Lead/applicant intake — not yet screened.
    "New lead": CanonicalStage.SOURCING,
    "Reached out": CanonicalStage.SOURCING,
    "Responded": CanonicalStage.SOURCING,
    "New applicant": CanonicalStage.SOURCING,
    # Internal screening/assessment stages.
    "Recruiter Phone Screen": CanonicalStage.SCREENING,
    "SparkHire Assessment Stage": CanonicalStage.SCREENING,
    "TestGorilla Assessment": CanonicalStage.SCREENING,
    # proposed default — needs business confirmation: SME Interview is an
    # internal subject-matter-expert vetting step, not yet client-facing.
    "SME Interview": CanonicalStage.SCREENING,
    "Predictive Talent Assessment": CanonicalStage.SCREENING,
    # Client-facing stages.
    "Presented to Customer": CanonicalStage.CLIENT_REVIEW,
    "Client Interview": CanonicalStage.INTERVIEWS,
    # proposed default — needs business confirmation: Reference check sits
    # in Lever's "offer" pipeline immediately before Offer (rank 260.5 vs
    # 261), so it's bucketed here rather than as its own canonical stage.
    "Reference check": CanonicalStage.OFFER,
    "Offer": CanonicalStage.OFFER,
    # proposed default — needs business confirmation: "Offer Declined" is
    # simultaneously a Lever *stage* and effectively a negative outcome;
    # bucketed as OFFER here since DijiOne has no "declined" canonical
    # stage — a negative Application.status should be set separately by
    # whatever consumes this (not this mapper's concern).
    "Offer Declined": CanonicalStage.OFFER,
}

# "Hired" is confirmed NOT a Lever pipeline stage — it is an Archive
# Reason. DEPLOYED has no Lever equivalent at all and must never be
# expected from Lever data; it is exclusively DijiOne-owned, post-hire
# state set by DijiTalentFlow's own workflow.

DEFAULT_STAGE = CanonicalStage.SOURCING


def map_lever_stage(stage_text: str) -> CanonicalStage:
    return LEVER_STAGE_MAP.get(stage_text, DEFAULT_STAGE)


# Real archive reasons confirmed by live tenant discovery. "Hired" is the
# only `type: "hired"` reason; every other configured reason is
# `type: "non-hired"`. Only "Withdrew" gets its own ApplicationStatus —
# every other non-hired reason collapses to REJECTED for the canonical
# field, with the raw text preserved separately on
# Application.lever_archive_reason for staff diagnostics.
_HIRED_REASON_TEXT = "hired"
_WITHDRAWN_REASON_TEXT = "withdrew"


def map_lever_archive_outcome(reason_text: str | None) -> ApplicationStatus:
    normalized = (reason_text or "").strip().lower()
    if normalized == _HIRED_REASON_TEXT:
        return ApplicationStatus.HIRED
    if normalized == _WITHDRAWN_REASON_TEXT:
        return ApplicationStatus.WITHDRAWN
    return ApplicationStatus.REJECTED
