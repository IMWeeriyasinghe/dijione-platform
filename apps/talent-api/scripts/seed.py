"""Seeds talent-api's local dev database: the TalentFlow-owned ``Client``
extension rows for the platform-owned canonical client set.

Run with:  python scripts/seed.py [--reset]

platform-api is the permanent owner of canonical Client/Organisation
identity (Architecture Completion Plan §6.1). This script fetches the real,
DTC-verified client directory from platform-api's running API
(``GET /api/platform/internal/clients``) and creates ONLY the local
``Client`` extension rows here (``platform_client_id`` + ``name``) — no
fake TalentRequest/Candidate/Application/Interview/Message/Document rows.

DijiTalentFlow real-data local validation (2026-09-01): this script
previously created a fixed set of entirely fictional demo business data (3
demo clients, 5 talent requests, 5 candidates — 3 of them falsely labeled
``source="LEVER"`` despite being 100% fictional — 6 applications, 2
interviews, 2 messages, 2 documents). That data is retired. Real TalentFlow
business data (Candidate/Application rows genuinely sourced from Lever) is
populated by the standard source-sync lifecycle
(``POST /api/recruitment/internal/sync`` on recruitment-api, followed by
TalentFlow's own DTC reconciliation), not by this script — see
docs/platform/data-ownership.md and CLAUDE.md's DIJIONE PLATFORM DATA
OWNERSHIP AND SOURCE SYNCHRONIZATION CONTRACT.

Run this script *after* platform-api's own seed, which populates the
canonical client directory this script reads.

REQUIRES platform-api to be running and reachable at ``PLATFORM_API_URL``
(default http://localhost:8000). This is a one-time local dev bootstrap
action, not a runtime request path, so a hard dependency here — unlike
``PlatformClient``'s normal best-effort/non-fatal runtime calls — is
acceptable (see docs/platform/local-development.md's "start platform-api
first" convention). Fails loudly, not silently, if platform-api is
unreachable or returns no clients.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from auth_client_py import PlatformClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.client import Client  # noqa: E402


def reset_schema() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _fetch_real_clients() -> list[dict]:
    settings = get_settings()
    client = PlatformClient(
        base_url=settings.platform_api_url, internal_secret=settings.internal_service_secret,
        timeout=10.0, caller="talent-api-seed",
    )
    try:
        resp = client.get_internal("/api/platform/internal/clients")
    except Exception as exc:
        raise RuntimeError(
            "Could not fetch the canonical client directory from platform-api "
            f"at {settings.platform_api_url}. platform-api must be running and "
            "already seeded (run its scripts/seed.py first) before running "
            f"this script. Original error: {exc}"
        ) from exc
    rows = resp.json()
    if not rows:
        raise RuntimeError(
            "platform-api returned zero clients. Run platform-api's "
            "scripts/seed.py [--reset] first."
        )
    return rows


def seed_client_extensions(db) -> int:
    """Get-or-create talent-api's Client extension row for every real,
    platform-owned client. Idempotent — matches by platform_client_id."""
    created = 0
    for row in _fetch_real_clients():
        existing = db.query(Client).filter_by(platform_client_id=row["public_id"]).one_or_none()
        if existing is None:
            db.add(
                Client(
                    platform_client_id=row["public_id"], name=row["name"],
                    status=row.get("status", "ACTIVE"),
                )
            )
            created += 1
        elif existing.name != row["name"]:
            existing.name = row["name"]
    db.commit()
    return created


def seed() -> None:
    db = SessionLocal()
    try:
        created = seed_client_extensions(db)
        total = db.query(Client).count()
        print("talent-api seed complete.")
        print(f"  Client extension rows: {total} total ({created} newly created)")
        print(
            "  No demo TalentRequest/Candidate/Application/Interview/Message/"
            "Document data is created by this script. Populate real business "
            "data via the recruitment-api sync + TalentFlow DTC reconciliation "
            "flow (POST /api/recruitment/internal/sync)."
        )
    finally:
        db.close()


if __name__ == "__main__":
    if "--reset" in sys.argv:
        reset_schema()
    seed()
