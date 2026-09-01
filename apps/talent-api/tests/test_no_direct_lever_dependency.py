"""Guard: DijiTalentFlow has ZERO direct dependency on Lever.

Lever is owned by the Recruitment Source domain (recruitment-api).
talent-api consumes it only over the ``RecruitmentSourceClient`` HTTP
contract. No file in ``app/`` may import ``app.integrations.lever``, call
``get_lever_client``, or reference a Lever API key/base URL.
"""

import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

_FORBIDDEN = (
    "get_lever_client",
    "app.integrations.lever",
    "from app.integrations.lever",
    "lever_api_key",
    "LiveLeverClient",
    "MockLeverClient",
    "app.recruitment_source",
)


def _rel(p: pathlib.Path) -> str:
    return p.relative_to(APP).as_posix()


def test_talentflow_has_no_direct_lever_dependency():
    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        hit = [tok for tok in _FORBIDDEN if tok in text]
        if hit:
            offenders.append(f"{_rel(path)}: {hit}")
    assert not offenders, (
        "Direct Lever dependency found in talent-api — consume recruitment-api "
        "via auth_client_py.RecruitmentSourceClient instead:\n" + "\n".join(offenders)
    )


def test_no_lever_integration_package_remains():
    assert not (APP / "integrations" / "lever").exists()
    assert not (APP / "recruitment_source").exists()
    assert not (APP / "services" / "lever_posting_service.py").exists()
