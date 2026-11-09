"""Disposable talent-api for the Playwright suites: synthetic data only.

Run by each app's playwright.config.ts. Refuses anything but a SQLite file in
the system temp folder, because it drops every table on start.
"""

import json
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

if os.environ.get("CONTAINER_APP_NAME") or os.environ.get("APP_ENV", "development") != "development":
    sys.exit("e2e_server never runs in a hosted environment")

port = int(sys.argv[1])
database = Path(tempfile.gettempdir()) / f"dijione-talent-e2e-{port}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{database.as_posix()}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402
from auth_client_py import PlatformClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from tests.conftest import issue_token, make_magic_link_grant  # noqa: E402

url = get_settings().database_url
if not url.startswith("sqlite:///") or Path(tempfile.gettempdir()).as_posix() not in url:
    sys.exit("e2e_server only runs against a temporary SQLite file")

from app.core.rate_limit import redeem_rate_limiter  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.application import Application  # noqa: E402
from app.models.candidate import Candidate  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.models.interview import Interview  # noqa: E402
from app.models.talent_request import TalentRequest  # noqa: E402

for method in ("record_audit_event", "notify_user", "broadcast_notification"):
    setattr(PlatformClient, method, lambda self, **kwargs: True)

# Every test redeems from one address; pytest covers the limiter itself.
redeem_rate_limiter.allow = lambda key: True

INTERNAL_NOTE = "internal-note-marker"
RECRUITER_NOTE = "recruiter-secret-marker"


def seed() -> dict:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    clients = {n: Client(name=f"{n} Test Co", status="ACTIVE", platform_client_id=f"cli-{n}") for n in ("Alpha", "Beta")}
    db.add_all(clients.values())
    db.commit()

    def request(code, client, title, *, pending=False):
        row = TalentRequest(
            request_code=code, client_id=client.id, designation=title, description="", required_skills="",
            seniority="", location="Remote", engagement_type="FULL_TIME", notes=INTERNAL_NOTE,
            current_stage="REQUEST_SUBMITTED" if pending else "SOURCING",
            lifecycle_status="PENDING_REVIEW" if pending else "IN_PROGRESS",
            customer_success_status="PENDING_REVIEW" if pending else "APPROVED",
            ta_status="NOT_STARTED" if pending else "IN_PROGRESS",
            client_safe_status_text="Sourcing candidates", priority="HIGH", created_by=1,
        )
        db.add(row)
        db.commit()
        return row

    def application(request_row, name, *, shared):
        person = Candidate(full_name=name, email=f"{name.split()[0].lower()}@example.invalid", professional_title="Tester")
        db.add(person)
        db.commit()
        row = Application(
            candidate_id=person.id, talent_request_id=request_row.id, current_stage="SCREENING", status="ACTIVE",
            is_client_visible=shared, recruiter_notes=RECRUITER_NOTE,
        )
        db.add(row)
        db.commit()
        return row

    def interview(row):
        when = datetime.now(UTC) + timedelta(days=2)
        db.add(Interview(application_id=row.id, scheduled_at=when, client_visible=True, notes=INTERNAL_NOTE))
        db.commit()

    alpha, beta = clients["Alpha"], clients["Beta"]
    alpha_request = request("SR-A1", alpha, "Alpha Engineer")
    pending = request("SR-A2", alpha, "Alpha Analyst", pending=True)
    beta_request = request("SR-B1", beta, "Beta Designer")
    sam = application(alpha_request, "Sam Shared", shared=True)
    hana = application(alpha_request, "Hana Hidden", shared=False)
    bella = application(beta_request, "Bella Beta", shared=True)
    interview(sam)
    interview(hana)
    interview(bella)

    grants = {
        "alpha": make_magic_link_grant(db, alpha),
        "beta": make_magic_link_grant(db, beta),
        "expired": make_magic_link_grant(db, alpha, expires_delta=timedelta(days=-1)),
        "revoked": make_magic_link_grant(db, alpha, revoked=True),
        "to_revoke": make_magic_link_grant(db, alpha),
    }
    state = {
        "api": f"http://127.0.0.1:{port}",
        "alpha": alpha.id, "beta": beta.id,
        "alpha_request": alpha_request.id, "pending_request": pending.id, "beta_request": beta_request.id,
        "sam": sam.id, "hana": hana.id, "bella": bella.id,
        "tokens": {k: v[1] for k, v in grants.items()},
        "to_revoke_id": grants["to_revoke"][0].public_id,
        "staff": {
            "ta": issue_token(201, full_name="Tara Member", role="TA_MEMBER"),
            "cs": issue_token(202, full_name="Casey Success", role="CUSTOMER_SUCCESS"),
            "restricted": issue_token(203, full_name="Riley Restricted", role="TA_MEMBER", client_ids=[alpha.id]),
            "client": issue_token(204, full_name="Cleo Client", role="TALENT_CLIENT", client_id=alpha.id),
        },
    }
    db.close()
    return state


Path(os.environ["E2E_STATE"]).write_text(json.dumps(seed()), encoding="utf-8")
uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
