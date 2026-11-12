from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.module_repo import ModuleRepository
from app.schemas.module import ModuleOut
from app.services.authorization_service import AuthorizationService

router = APIRouter(prefix="/api/modules", tags=["modules"])


@router.get("", response_model=list[ModuleOut])
def list_my_modules(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ModuleOut]:
    """Only modules the current user is authorized to see (CLAUDE.md §9)."""
    modules = ModuleRepository(db).list_enabled()
    # Effective access — the same direct + active-group grants that build the
    # JWT module_roles claim — so group-granted modules appear on Home too.
    user_module_keys = set(AuthorizationService(db).effective_module_roles(user))

    visible = []
    for module in modules:
        required = [r for r in module.required_roles.split(",") if r]
        if not required or module.key in user_module_keys:
            visible.append(module)
    return visible
