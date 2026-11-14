"""Bulk import of HR-approved verified mappings (dry-run mandatory, atomic).

Only a file in the exact approved format is accepted — the raw HR workbook
or any other export is rejected by header. Every row must carry its own
verification evidence (``evidence``, ``verified_by``, ``verified_on``,
``source_reference``); a row missing any of it is an ERROR, never a warning.

``apply`` requires the token of a dry-run of the *same bytes* by the *same
administrator* issued within ``TOKEN_TTL_SECONDS``, re-validates everything,
and writes all rows plus their history in ONE transaction: any failure rolls
back the whole batch (mappings and history alike). Nothing is committed per
row. Platform audit events are sent only after the commit.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
import time
import uuid
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.identity import SOURCE_IMPORT
from app.repositories.identity_repository import IdentityRepository
from app.services import platform_audit
from app.services.identity_admin_service import (
    MIN_TEXT,
    Actor,
    IdentityError,
    MappingInput,
    _insert_mapping,
    evidence_warnings,
    mapping_out,
)
from app.services.workforce_directory import DirectorySnapshot

REQUIRED_HEADER = ["site_id", "zk_emp_code", "bamboohr_id", "valid_from", "valid_to", "evidence", "verified_by",
                   "verified_on", "source_reference"]
MAX_ROWS = 5000
MAX_BYTES = 2_000_000
TOKEN_TTL_SECONDS = 30 * 60


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sign(file_hash: str, actor_id: int, issued: int) -> str:
    key = get_settings().internal_service_secret.encode()
    return hmac.new(key, f"{file_hash}|{actor_id}|{issued}".encode(), hashlib.sha256).hexdigest()


def make_token(content: bytes, actor_id: int, issued: int | None = None) -> str:
    issued = int(time.time()) if issued is None else issued
    return f"{issued}.{_sign(_digest(content), actor_id, issued)}"


def check_token(token: str | None, content: bytes, actor_id: int) -> None:
    try:
        issued_s, sig = (token or "").split(".", 1)
        issued = int(issued_s)
    except ValueError:
        raise IdentityError(422, {"error": "DRY_RUN_REQUIRED",
                                  "message": "Run a dry-run of this exact file first."}) from None
    if not hmac.compare_digest(sig, _sign(_digest(content), actor_id, issued)):
        raise IdentityError(422, {"error": "DRY_RUN_MISMATCH",
                                  "message": "The dry-run token does not match this file and administrator."})
    if time.time() - issued > TOKEN_TTL_SECONDS:
        raise IdentityError(422, {"error": "DRY_RUN_EXPIRED", "message": "The dry-run is older than 30 minutes."})


def _parse(content: bytes) -> list[dict]:
    if len(content) > MAX_BYTES:
        raise IdentityError(413, {"error": "FILE_TOO_LARGE", "message": "Import file is too large."})
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise IdentityError(422, {"error": "NOT_UTF8", "message": "Import file must be UTF-8 CSV."}) from None
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if header is None or [h.strip() for h in header] != REQUIRED_HEADER:
        raise IdentityError(422, {"error": "INVALID_HEADER", "expected": REQUIRED_HEADER,
                                  "message": "Only the approved verified-mappings format can be imported."})
    rows = []
    for n, raw in enumerate(reader, start=2):
        if not any(c.strip() for c in raw):
            continue
        if len(raw) != len(REQUIRED_HEADER):
            rows.append({"line": n, "_malformed": True})
            continue
        rows.append({"line": n, **dict(zip(REQUIRED_HEADER, raw, strict=True))})
    if len(rows) > MAX_ROWS:
        raise IdentityError(413, {"error": "TOO_MANY_ROWS", "message": f"At most {MAX_ROWS} rows per import."})
    if not rows:
        raise IdentityError(422, {"error": "EMPTY_FILE", "message": "The file has no data rows."})
    return rows


def _date(v: str) -> date | None:
    v = (v or "").strip()
    return date.fromisoformat(v) if v else None


def _static_errors(actor: Actor, people: dict, r: dict, today: date) -> tuple[list[str], dict]:
    errors: list[str] = []
    site, code, bid = r["site_id"].strip(), r["zk_emp_code"], r["bamboohr_id"].strip()
    vf = vt = von = None
    try:
        vf, vt = _date(r["valid_from"]), _date(r["valid_to"])
    except ValueError:
        errors.append("INVALID_DATE")
    try:
        von = _date(r["verified_on"])
    except ValueError:
        errors.append("INVALID_VERIFIED_ON")
    if site not in actor.allowed_site_ids:
        errors.append("SITE_NOT_ALLOWED")
    if not code or code != code.strip() or len(code) > 20:
        errors.append("INVALID_CODE")
    if bid not in people:
        errors.append("UNKNOWN_EMPLOYEE")
    if vf is None and "INVALID_DATE" not in errors:
        errors.append("VALID_FROM_REQUIRED")
    if vf and vt and vt < vf:
        errors.append("INVALID_PERIOD")
    if len(r["evidence"].strip()) < MIN_TEXT:
        errors.append("EVIDENCE_REQUIRED")
    if not r["verified_by"].strip():
        errors.append("VERIFIED_BY_REQUIRED")
    if von is None and "INVALID_VERIFIED_ON" not in errors:
        errors.append("VERIFIED_ON_REQUIRED")
    if von and von > today:
        errors.append("VERIFIED_ON_IN_FUTURE")
    if not r["source_reference"].strip():
        errors.append("SOURCE_REFERENCE_REQUIRED")
    return errors, {"site_id": site, "zk_emp_code": code, "bamboohr_id": bid, "valid_from": vf, "valid_to": vt}


def _simulate(db: Session, actor: Actor, directory: DirectorySnapshot, rows: list[dict], today: date,
              batch: str) -> tuple[list[dict], list]:
    """Validate every row and insert them in file order inside the CURRENT
    transaction (never committed here), so in-file interactions — two rows for
    one code, one employee with several codes — are checked exactly as an
    apply would see them. Returns (report, created mappings)."""
    if not directory.available:
        raise IdentityError(503, {"error": "DIRECTORY_UNAVAILABLE", "message": "The Workforce Directory is unavailable."})
    people = directory.by_bamboohr_id()
    report, parsed = [], []
    for r in rows:
        if r.get("_malformed"):
            report.append({"line": r["line"], "errors": ["MALFORMED_ROW"], "warnings": []})
            parsed.append(None)
            continue
        errors, p = _static_errors(actor, people, r, today)
        report.append({"line": r["line"], "site_id": p["site_id"], "zk_emp_code": p["zk_emp_code"],
                       "bamboohr_id": p["bamboohr_id"],
                       "employee_name": people.get(p["bamboohr_id"], {}).get("display_name"),
                       "valid_from": p["valid_from"].isoformat() if p["valid_from"] else None,
                       "valid_to": p["valid_to"].isoformat() if p["valid_to"] else None,
                       "errors": errors, "warnings": []})
        parsed.append(p)
    if any(r["errors"] for r in report):
        return report, []  # static errors: nothing is inserted
    created = []
    for raw, rep, p in zip(rows, report, parsed, strict=True):
        warnings = evidence_warnings(db, actor, directory, p["site_id"], p["zk_emp_code"], p["bamboohr_id"],
                                     p["valid_from"], p["valid_to"])
        rep["warnings"] = warnings
        evidence = (f"{raw['evidence'].strip()} | verified_by: {raw['verified_by'].strip()} | "
                    f"verified_on: {raw['verified_on'].strip()} | source: {raw['source_reference'].strip()}")
        try:
            created.append(_insert_mapping(db, actor, directory, MappingInput(
                site_id=p["site_id"], zk_emp_code=p["zk_emp_code"], bamboohr_id=p["bamboohr_id"],
                valid_from=p["valid_from"], valid_to=p["valid_to"], evidence=evidence,
                acknowledged_warnings=tuple(w["code"] for w in warnings)),
                source=SOURCE_IMPORT, import_batch_id=batch))
        except IdentityError as exc:
            rep["errors"].append((exc.detail or {}).get("error", "INVALID") if isinstance(exc.detail, dict)
                                 else "INVALID")
    return report, created


def _summary(report: list[dict]) -> dict:
    return {"rows": len(report), "rows_with_errors": sum(1 for r in report if r["errors"]),
            "rows_with_warnings": sum(1 for r in report if r["warnings"]),
            "warning_codes": sorted({w["code"] for r in report for w in r["warnings"]})}


def dry_run(db: Session, actor: Actor, directory: DirectorySnapshot, content: bytes, *,
            today: date | None = None) -> dict:
    """Full validation by simulation; ALWAYS rolled back — a dry-run never persists anything."""
    try:
        report, _ = _simulate(db, actor, directory, _parse(content), today or date.today(), batch="dry-run")
    finally:
        db.rollback()
    s = _summary(report)
    return {"dry_run": True, "file_sha256": _digest(content), "summary": s, "rows": report,
            "can_apply": s["rows_with_errors"] == 0,
            "requires_warning_acknowledgement": s["rows_with_warnings"] > 0,
            "dry_run_token": make_token(content, actor.user_id) if s["rows_with_errors"] == 0 else None}


def apply(db: Session, actor: Actor, directory: DirectorySnapshot, content: bytes, *, token: str | None,
          acknowledge_warnings: bool, today: date | None = None) -> dict:
    """All-or-nothing: every mapping and every history row of the batch are
    committed together, or nothing is."""
    check_token(token, content, actor.user_id)
    rows = _parse(content)
    batch = str(uuid.uuid4())
    try:
        report, created = _simulate(db, actor, directory, rows, today or date.today(), batch=batch)
        s = _summary(report)
        if s["rows_with_errors"]:
            raise IdentityError(422, {"error": "IMPORT_HAS_ERRORS", "summary": s, "rows": report})
        if s["rows_with_warnings"] and not acknowledge_warnings:
            raise IdentityError(422, {"error": "WARNINGS_NOT_ACKNOWLEDGED", "summary": s, "rows": report})
        IdentityRepository(db).add_event(
            entity_type="IMPORT", entity_id=0, action="IMPORT_APPLIED", actor_user_id=actor.user_id,
            new={"batch_id": batch, "file_sha256": _digest(content), "rows": len(created),
                 "mapping_ids": [m.id for m in created]}, note=f"import {batch}")
        db.commit()
    except Exception:
        db.rollback()  # no mapping and no history row survives a failed batch
        raise
    platform_audit.record(actor_id=actor.user_id, action="onsite.identity.import.applied",
                          entity_type="OnsiteIdentityImport", entity_id=0, previous=None,
                          new={"batch_id": batch, "rows": len(created), "file_sha256": _digest(content)})
    return {"applied": True, "batch_id": batch, "summary": s,
            "mappings": [mapping_out(m, directory) for m in created]}
