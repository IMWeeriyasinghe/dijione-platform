"""Guard: after the Recruitment Source extraction, DijiTalentFlow's consumer
surface must NOT acquire a direct runtime dependency on the Lever client.

Lever access is owned by the bounded ``app/recruitment_source/`` module
(promotion target: ``apps/recruitment-api``). The consumer route
(``recruitment.py``) and any future TalentFlow business code must go through
that module's service, never ``get_lever_client`` / ``app.integrations.lever``
directly.

``app/api/routes/integrations.py`` is the pre-extraction legacy status
surface — explicitly allow-listed here and slated for removal when the
module is lifted into its own service.
"""

import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

_LEVER_TOKENS = ("get_lever_client", "app.integrations.lever", "from app.integrations.lever")

# Files permitted to touch the Lever client directly (the owner + adapters +
# the reconciliation services it wraps + the one legacy status route).
_ALLOWLIST_DIRS = ("recruitment_source", "integrations")
_ALLOWLIST_FILES = {
    "services/lever_posting_service.py",
    "services/lever_contact_application_sync_service.py",
    "services/sync_service.py",
    "api/routes/integrations.py",  # legacy — remove on service lift
}


def _rel(p: pathlib.Path) -> str:
    return p.relative_to(APP).as_posix()


def test_talentflow_consumer_surface_has_no_direct_lever_import():
    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        rel = _rel(path)
        if any(part in rel.split("/") for part in _ALLOWLIST_DIRS):
            continue
        if rel in _ALLOWLIST_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        if any(tok in text for tok in _LEVER_TOKENS):
            offenders.append(rel)
    assert not offenders, (
        "Direct Lever dependency found outside the Recruitment Source module: "
        f"{offenders}. Consume it via app/recruitment_source/service.py instead."
    )


def test_recruitment_consumer_route_does_not_import_lever_client():
    text = (APP / "api" / "routes" / "recruitment.py").read_text(encoding="utf-8")
    assert "get_lever_client" not in text
    assert "app.integrations.lever" not in text
