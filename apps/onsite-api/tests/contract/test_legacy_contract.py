"""Legacy API contract baselines (Stage 0 of the identity redesign).

The fixtures under ``tests/contract/fixtures`` were captured from the
UNCHANGED release line (origin/release/onsite-v1 @ 7eabdc6) before any
identity-resolution behaviour was modified. They record the *shape* of every
viewer and admin response the current onsite-web consumes — key sets, value
types, enum vocabularies, workbook sheet names and header rows — never the
values. The compatibility shim introduced in Stage 3 must keep this suite
green while ``ONSITE_LEGACY_CONTRACT`` is on.

Re-capturing (``CONTRACT_CAPTURE=1 pytest tests/contract``) is only
legitimate on the unchanged tree; doing so after Stage 1 would silently
move the baseline and must be called out explicitly in review.

Since Stage 3 the check is BACKWARD COMPATIBILITY, not equality:
- every key of the baseline shape is still present with a compatible type
  (additive new-contract keys such as ``bamboohr_id``/``mapping_status`` are
  allowed);
- enum values may only come from the baseline vocabulary (no new
  ``identity_class``/flag values reach the running onsite-web), while
  ``review_breakdown``/``counts`` must still carry every baseline key.
Data comes from explicit synthetic VERIFIED mappings (``map_directory``).
Excel files are downloads, not parsed by the web app: their sheet names are
held to the baseline, while their column headers changed deliberately
(``Employee Number`` was the ZKBioTime ID) and are asserted explicitly in
``NEW_EXPORT_HEADERS``.
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest
from openpyxl import load_workbook

from tests.conftest import DIRECTORY, enable_site, headers_for, map_directory, run_sync

FIXTURES = Path(__file__).parent / "fixtures"
WEB_FIXTURES = Path(__file__).resolve().parents[4] / "apps" / "onsite-web" / "src" / "__tests__" / "fixtures" / "api-legacy"
CAPTURE = os.environ.get("CONTRACT_CAPTURE") == "1"

DAY1, DAY2 = "2026-10-13", "2026-10-14"
SITE = "dev-site"
ENUM_KEYS = {"identity_class", "flags", "flag", "feed_state", "status", "employment_status", "identity_classification"}

# name -> (path, role). Shapes are captured per endpoint; the role is the
# least-privileged one that may call it today.
JSON_ENDPOINTS: dict[str, tuple[str, str]] = {
    "me": ("/api/onsite/me", "ONSITE_VIEWER"),
    "summary": ("/api/onsite/summary", "ONSITE_VIEWER"),
    "freshness": ("/api/onsite/freshness", "ONSITE_VIEWER"),
    "sites": ("/api/onsite/sites", "ONSITE_VIEWER"),
    "overview": (f"/api/onsite/dashboard/overview?site_id={SITE}&date={DAY1}", "ONSITE_VIEWER"),
    "hourly_activity": (f"/api/onsite/dashboard/hourly-activity?site_id={SITE}&date={DAY1}", "ONSITE_VIEWER"),
    "activity_trend": (f"/api/onsite/dashboard/activity-trend?site_id={SITE}&days=7", "ONSITE_VIEWER"),
    "recent_activity": (f"/api/onsite/dashboard/recent-activity?site_id={SITE}", "ONSITE_VIEWER"),
    "today": (f"/api/onsite/today?site_id={SITE}&date={DAY1}", "ONSITE_VIEWER"),
    "activity": (f"/api/onsite/activity?site_id={SITE}&date_from={DAY1}&date_to={DAY2}", "ONSITE_VIEWER"),
    "activity_events": (f"/api/onsite/activity?site_id={SITE}&date_from={DAY1}&date_to={DAY2}&emp_code=101",
                        "ONSITE_VIEWER"),
    "employees": (f"/api/onsite/employees?site_id={SITE}&date_from={DAY1}&date_to={DAY2}", "ONSITE_VIEWER"),
    "employee_detail": (f"/api/onsite/employees/101?site_id={SITE}&date_from={DAY1}&date_to={DAY2}", "ONSITE_VIEWER"),
    "exceptions": (f"/api/onsite/exceptions?site_id={SITE}&date_from={DAY1}&date_to={DAY2}", "ONSITE_VIEWER"),
    "admin_identity_match": ("/api/onsite/admin/identity-match", "ONSITE_ADMIN"),
    "admin_identity_match_paged": ("/api/onsite/admin/identity-match?page=1&page_size=10", "ONSITE_ADMIN"),
    "admin_sites": ("/api/onsite/admin/sites", "ONSITE_ADMIN"),
    "admin_health": ("/api/onsite/admin/health", "ONSITE_ADMIN"),
}
XLSX_ENDPOINTS: dict[str, tuple[str, str]] = {
    "export_today": (f"/api/onsite/today/export?site_id={SITE}&date={DAY1}", "ONSITE_VIEWER"),
    "export_activity": (f"/api/onsite/activity/export?site_id={SITE}&date_from={DAY1}&date_to={DAY2}", "ONSITE_VIEWER"),
    "export_employees": (f"/api/onsite/employees/export?site_id={SITE}&date_from={DAY1}&date_to={DAY2}",
                         "ONSITE_VIEWER"),
    "export_exceptions": (f"/api/onsite/exceptions/export?site_id={SITE}&date_from={DAY1}&date_to={DAY2}",
                          "ONSITE_VIEWER"),
    "export_overview": (f"/api/onsite/dashboard/overview/export?site_id={SITE}&date={DAY1}", "ONSITE_VIEWER"),
}
CSV_ENDPOINTS: dict[str, tuple[str, str]] = {
    "activity_csv": (f"/api/onsite/activity?site_id={SITE}&date_from={DAY1}&date_to={DAY2}&format=csv", "ONSITE_VIEWER"),
    "admin_identity_match_csv": ("/api/onsite/admin/identity-match?format=csv", "ONSITE_ADMIN"),
}
STATUS_ENDPOINTS: dict[str, tuple[str, str, int]] = {
    # Photo for a code with no photo in the directory -> 404 today; the shim must keep that.
    "employee_photo_404": ("/api/onsite/employees/101/photo", "ONSITE_VIEWER", 404),
    "employee_detail_unknown_404": (f"/api/onsite/employees/NOPE?site_id={SITE}", "ONSITE_VIEWER", 404),
}


# --- shape derivation ---------------------------------------------------------

def _scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    return "str"


def _merge(a, b):
    """Merge two shapes (union of keys, '|'-joined scalar types)."""
    if isinstance(a, dict) and isinstance(b, dict):
        return {k: _merge(a.get(k), b.get(k)) if k in a and k in b else (a.get(k) if k in a else b.get(k))
                for k in sorted(set(a) | set(b))}
    if isinstance(a, list) and isinstance(b, list):
        if not a:
            return b
        if not b:
            return a
        return [_merge(a[0], b[0])]
    if isinstance(a, str) and isinstance(b, str):
        return "|".join(sorted(set(a.split("|")) | set(b.split("|"))))
    return a if b is None else b


def shape(v):
    if isinstance(v, dict):
        return {k: shape(x) for k, x in sorted(v.items())}
    if isinstance(v, list):
        out = None
        for x in v:
            out = shape(x) if out is None else _merge(out, shape(x))
        return [out] if out is not None else []
    return _scalar(v)


def enums(v, path: str = "", acc: dict | None = None) -> dict:
    """Collect the vocabularies of enum-like keys wherever they appear."""
    acc = {} if acc is None else acc
    if isinstance(v, dict):
        for k, x in v.items():
            if k in ENUM_KEYS and isinstance(x, (str, type(None))):
                acc.setdefault(k, set()).add(x if x is not None else "null")
            elif k in ENUM_KEYS and isinstance(x, list) and all(isinstance(i, str) for i in x):
                acc.setdefault(k, set()).update(x)
            elif k == "review_breakdown" and isinstance(x, dict):
                acc.setdefault("review_breakdown_keys", set()).update(x.keys())
            elif k == "counts" and isinstance(x, dict):
                acc.setdefault("exception_count_keys", set()).update(x.keys())
            else:
                enums(x, f"{path}.{k}", acc)
    elif isinstance(v, list):
        for x in v:
            enums(x, path, acc)
    return acc


def _enums_json(e: dict) -> dict:
    return {k: sorted(vals) for k, vals in sorted(e.items())}


def workbook_shape(content: bytes) -> dict:
    wb = load_workbook(io.BytesIO(content), read_only=True)
    out = {}
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c) for c in row]
            rows.append(cells)
            # stop after the header row: the first row with >= 5 non-empty cells
            if sum(1 for c in cells if c) >= 5:
                break
        # Preamble values (site, dates, filters) vary; keep labels (first cell) and the header row verbatim.
        preamble = [r[0] for r in rows[:-1]]
        header = rows[-1] if rows else []
        out[ws.title] = {"preamble_labels": preamble, "header": header}
    return out


# --- fixture plumbing ---------------------------------------------------------

def _ready(api_client):
    if not CAPTURE:
        map_directory(DIRECTORY)
    run_sync(api_client)
    enable_site(api_client, SITE)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _store(name: str, data: dict) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / f"{name}.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _store_web_sample(name: str, body) -> None:
    WEB_FIXTURES.mkdir(parents=True, exist_ok=True)
    (WEB_FIXTURES / f"{name}.json").write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")


_SUPERSET_ENUMS = {"review_breakdown_keys", "exception_count_keys"}


def compatible(expected, observed, path: str = "$") -> list[str]:
    """Problems that would break a consumer written against ``expected``."""
    if isinstance(expected, dict):
        if not isinstance(observed, dict):
            return [f"{path}: expected object"]
        out = []
        for k, v in expected.items():
            if k not in observed:
                out.append(f"{path}.{k}: missing")
            else:
                out += compatible(v, observed[k], f"{path}.{k}")
        return out
    if isinstance(expected, list):
        if not isinstance(observed, list):
            return [f"{path}: expected array"]
        if not expected or not observed:
            return []
        return compatible(expected[0], observed[0], f"{path}[]")
    if isinstance(observed, (dict, list)):
        return [f"{path}: expected scalar"]
    allowed = set(expected.split("|")) | ({"int"} if "float" in expected else set())
    extra = set(observed.split("|")) - allowed
    return [f"{path}: new type(s) {sorted(extra)} (baseline {expected})"] if extra else []


def enum_problems(expected: dict, observed: dict) -> list[str]:
    out = []
    for k, vals in observed.items():
        base = set(expected.get(k, []))
        if k in _SUPERSET_ENUMS:
            if base - set(vals):
                out.append(f"{k}: lost {sorted(base - set(vals))}")
        elif k in expected and set(vals) - base:
            out.append(f"{k}: new values {sorted(set(vals) - base)}")
        elif k not in expected and k in ENUM_KEYS:
            out.append(f"{k}: enum not in baseline")
    return out


def _check(name: str, observed: dict) -> None:
    if CAPTURE:
        _store(name, observed)
        return
    expected = _load(name)
    assert observed["status"] == expected["status"]
    if "shape" in expected:
        problems = compatible(expected["shape"], observed["shape"]) + enum_problems(expected["enums"],
                                                                                    observed["enums"])
        assert not problems, f"legacy contract broken in {name}: {problems}"
    elif "sheets" in expected:
        assert sorted(observed["sheets"]) == sorted(SHEET_RENAMES.get(x, x) for x in expected["sheets"]), name
        for old_sheet, exp in expected["sheets"].items():
            sheet = SHEET_RENAMES.get(old_sheet, old_sheet)
            obs = observed["sheets"][sheet]
            if sheet in NEW_EXPORT_HEADERS:  # tabular report sheets
                renamed = [LABEL_RENAMES.get(x, x) for x in exp["preamble_labels"]]
                assert obs["preamble_labels"] == renamed, (name, sheet)
                assert obs["header"] == NEW_EXPORT_HEADERS[sheet], (name, sheet)
            else:  # measure sheets (Summary, Hourly Activity, 30-Day Trend): row labels only
                want = {LABEL_RENAMES.get(x, x) for x in _labels(exp)} - REMOVED_MEASURES
                got = _labels(obs) - ADDED_MEASURES
                assert got == want, (name, sheet, sorted(got ^ want))
    else:
        assert observed == expected, name


def _labels(sheet: dict) -> set[str]:
    """First-column labels of a measure sheet, ignoring date/time/number rows."""
    vals = list(sheet["preamble_labels"]) + ([sheet["header"][0]] if sheet["header"] else [])
    return {v for v in vals if v and not v[:1].isdigit()}


# Deliberate, reviewed export changes (identity redesign, Stage 3).
REMOVED_MEASURES = {"Unmatched codes"}  # unmapped IDs are no longer part of attendance reports
ADDED_MEASURES = {"Unmapped punches excluded (see Identity Management)"}
LABEL_RENAMES = {
    "Employee Number": "ZKBioTime ID",
    # Diji On-site terminology standard (2026-11-14): people are "team members".
    "Employee search": "Team member search", "Employees with activity": "Team members with activity",
    "Employee-days with activity": "Team-member days with activity", "Employees needing review": "Team members needing review",
    "Employees listed": "Team members listed", "Employees with review flags": "Team members with review flags",
    "Single-activity employees": "Single-activity team members", "Employees": "Team Members",
    "Employee Activity Report": "Team Member Activity Report",
    "Employee Activity Report — Summary": "Team Member Activity Report — Summary",
    "Review flag: Inactive employee activity": "Review flag: Inactive team member activity",
}
SHEET_RENAMES = {"Employees": "Team Members"}
NEW_EXPORT_HEADERS = {
    "Attendance Report": ["Date", "Team Member Name", "BHR Employee ID", "EMP Number", "ZKBioTime ID(s)",
                          "Department", "Employment Status", "First Activity", "Latest Activity", "Punch Count",
                          "Activity Span (minutes)", "Terminal(s)", "Mapping Status", "Review Flags"],
    "Exception Report": ["Date", "Team Member Name", "BHR Employee ID", "EMP Number", "ZKBioTime ID(s)",
                         "Department", "Employment Status", "First Activity", "Latest Activity", "Punch Count",
                         "Activity Span (minutes)", "Terminal(s)", "Mapping Status", "Review Flags", "Review Reasons"],
    "Event Detail": ["Local Date", "Local Time", "ZKBioTime ID", "Team Member Name", "BHR Employee ID",
                     "EMP Number", "Department", "Terminal", "Verify Type", "Mapping Status",
                     "Review Flags"],
    "Team Members": ["Team Member Name", "BHR Employee ID", "EMP Number", "ZKBioTime ID(s)", "Department",
                  "Employment Status", "Mapping Status", "Activity Days", "Attendance Events", "Review Flags",
                  "Last Activity (site local)"],
}


# --- tests --------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(JSON_ENDPOINTS))
def test_json_contract(name, api_client, db, audit_calls, directory):
    _ready(api_client)
    path, role = JSON_ENDPOINTS[name]
    resp = api_client.get(path, headers=headers_for(role))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    observed = {"status": 200, "shape": shape(body), "enums": _enums_json(enums(body))}
    if CAPTURE:
        _store_web_sample(name, body)
    _check(name, observed)


@pytest.mark.parametrize("name", sorted(XLSX_ENDPOINTS))
def test_xlsx_contract(name, api_client, db, audit_calls, directory):
    _ready(api_client)
    path, role = XLSX_ENDPOINTS[name]
    resp = api_client.get(path, headers=headers_for(role))
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/vnd.openxmlformats")
    _check(name, {"status": 200, "sheets": workbook_shape(resp.content)})


@pytest.mark.parametrize("name", sorted(CSV_ENDPOINTS))
def test_csv_contract(name, api_client, db, audit_calls, directory):
    _ready(api_client)
    path, role = CSV_ENDPOINTS[name]
    resp = api_client.get(path, headers=headers_for(role))
    assert resp.status_code == 200, resp.text
    header = resp.text.splitlines()[0]
    _check(name, {"status": 200, "content_type": resp.headers["content-type"].split(";")[0], "header": header})


@pytest.mark.parametrize("name", sorted(STATUS_ENDPOINTS))
def test_status_contract(name, api_client, db, audit_calls, directory):
    _ready(api_client)
    path, role, expected = STATUS_ENDPOINTS[name]
    resp = api_client.get(path, headers=headers_for(role))
    assert resp.status_code == expected, resp.text


def test_viewer_is_denied_admin_routes(api_client, db, audit_calls, directory):
    """Permission boundary that the shim must preserve unchanged."""
    _ready(api_client)
    for path in ("/api/onsite/admin/identity-match", "/api/onsite/admin/sites", "/api/onsite/admin/health"):
        assert api_client.get(path, headers=headers_for("ONSITE_VIEWER")).status_code == 403, path
    assert api_client.get("/api/onsite/summary").status_code == 401
