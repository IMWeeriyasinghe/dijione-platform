"""Maps Lever's actual pipeline stage names into DijiOne's fixed canonical
client-facing stages (CLAUDE.md §30). Update LEVER_STAGE_MAP after live
Lever discovery (Phase D/E) — nothing else in the app should need to
change, since routes/UI only ever see CanonicalStage values.
"""

from app.core.constants import CanonicalStage

LEVER_STAGE_MAP: dict[str, CanonicalStage] = {
    "New Lead": CanonicalStage.SOURCING,
    "Sourced": CanonicalStage.SOURCING,
    "Applicant Review": CanonicalStage.SCREENING,
    "Recruiter Screen": CanonicalStage.SCREENING,
    "Phone Screen": CanonicalStage.SCREENING,
    "Client Submission": CanonicalStage.CLIENT_REVIEW,
    "Client Review": CanonicalStage.CLIENT_REVIEW,
    "Interview": CanonicalStage.INTERVIEWS,
    "Onsite Interview": CanonicalStage.INTERVIEWS,
    "Offer": CanonicalStage.OFFER,
    "Offer Extended": CanonicalStage.OFFER,
    "Hired": CanonicalStage.ONBOARDING,
    "Background Check": CanonicalStage.ONBOARDING,
    "Deployed": CanonicalStage.DEPLOYED,
}

DEFAULT_STAGE = CanonicalStage.SOURCING


def map_lever_stage(stage_text: str) -> CanonicalStage:
    return LEVER_STAGE_MAP.get(stage_text, DEFAULT_STAGE)
