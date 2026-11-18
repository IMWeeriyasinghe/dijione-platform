"""Pre-rollback check for delegated application access.

    python -m app.services.delegated_access_rollback

Run it before deploying a platform-api image older than this feature (or downgrading the
migration). An older image does not know application suspensions, so anyone suspended would get
their group access back. The check lists every appointment and suspension and exits 1 while any
exist. Removing them is a deliberate, audited Central Admin action (remove the appointment; for a
suspension, remove the person from the group or the group's grant, then lift the suspension).
The check never changes anything, and nothing here touches group assignments.

Switching the feature off (DELEGATED_ACCESS_ENABLED=false) is always safe and needs none of this:
the current image keeps enforcing suspensions.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.application_access import ApplicationAccessSuspension, ApplicationAdministrator
from app.models.user import User


@dataclass(frozen=True)
class RollbackReadiness:
    appointments: list[tuple[str, str]]  # (module, email)
    suspensions: list[tuple[str, str]]

    @property
    def safe(self) -> bool:
        return not self.appointments and not self.suspensions


def check(db: Session) -> RollbackReadiness:
    def rows(model):
        return sorted(
            (module_key, email)
            for module_key, email in db.execute(
                select(model.module_key, User.email).join(User, User.id == model.user_id)
            ).all()
        )

    return RollbackReadiness(appointments=rows(ApplicationAdministrator), suspensions=rows(ApplicationAccessSuspension))


def main() -> int:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        result = check(db)
    for module_key, email in result.appointments:
        print(f"appointment  {module_key:<12} {email}")
    for module_key, email in result.suspensions:
        print(f"suspension   {module_key:<12} {email}")
    if result.safe:
        print("SAFE: no appointments or suspensions; an older platform-api image restores no access.")
        return 0
    print(
        "NOT SAFE: an older platform-api image would ignore the suspensions above and restore group access. "
        "Remove them deliberately in Central Admin first, or switch the feature off instead (always safe)."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
