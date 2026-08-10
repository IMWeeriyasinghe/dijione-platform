from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.module_repo import ModuleRepository
from app.repositories.user_repo import UserRepository
from app.schemas.module import ModuleOut

router = APIRouter(prefix="/api/modules", tags=["modules"])


@router.get("", response_model=list[ModuleOut])
def list_my_modules(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ModuleOut]:
    """Only modules the current user is authorized to see (CLAUDE.md §9)."""
    modules = ModuleRepository(db).list_enabled()
    user_module_keys = {r.module_key for r in UserRepository(db).module_roles_for(user.id)}

    visible = []
    for module in modules:
        required = [r for r in module.required_roles.split(",") if r]
        if not required or module.key in user_module_keys:
            visible.append(module)
    return visible
