"""Guard: DijiBirthday has ZERO direct dependency on BambooHR.

BambooHR is owned by the People / Workforce domain (people-api).
birthday-api consumes it only over ``auth_client_py.EmployeeDirectoryClient``
(via ``app/integrations/people_source/http_adapter.py``). No file in
``app/`` may import ``app.integrations.bamboohr`` or reference a BambooHR
API key/subdomain.
"""

import pathlib

APP = pathlib.Path(__file__).resolve().parents[1] / "app"

_FORBIDDEN = (
    "app.integrations.bamboohr",
    "from app.integrations.bamboohr",
    "bamboohr_api_key",
    "bamboohr_subdomain",
    "BambooHRHttpClient",
    "BambooHRClient",
)


def _rel(p: pathlib.Path) -> str:
    return p.relative_to(APP).as_posix()


def test_birthday_has_no_direct_bamboohr_dependency():
    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        hit = [tok for tok in _FORBIDDEN if tok in text]
        if hit:
            offenders.append(f"{_rel(path)}: {hit}")
    assert not offenders, (
        "Direct BambooHR dependency found in birthday-api — consume people-api "
        "via auth_client_py.EmployeeDirectoryClient instead:\n" + "\n".join(offenders)
    )


def test_no_bamboohr_integration_package_remains():
    assert not (APP / "integrations" / "bamboohr").exists()
