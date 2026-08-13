"""Service-to-service read surface — admin-api uses this to resolve client
display names for the Admin Center's client-scope picker/effective-access
view, since it has no talent-flow module role of its own to see
``/api/talent/clients`` with (CR §38: admin must work even for an
administrator who holds no DijiTalentFlow role)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import require_internal_service
from app.db.session import get_db
from app.repositories.client_repo import ClientRepository

router = APIRouter(prefix="/api/talent/internal", tags=["talent-internal"])


@router.get("/clients-lite")
def clients_lite(
    db: Session = Depends(get_db), _service: None = Depends(require_internal_service)
) -> list[dict]:
    return [{"id": c.id, "name": c.name} for c in ClientRepository(db).list_all()]
