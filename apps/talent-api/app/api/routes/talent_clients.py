from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, require_staff_scope
from app.db.session import get_db
from app.repositories.client_repo import ClientRepository
from app.schemas.client import ClientOut, ClientPortfolioOut

router = APIRouter(prefix="/api/talent/clients", tags=["talent-clients"])


@router.get("", response_model=list[ClientPortfolioOut])
def list_client_portfolios(
    scope: TalentScope = Depends(require_staff_scope), db: Session = Depends(get_db)
) -> list[ClientPortfolioOut]:
    """Cross-client portfolio view — staff only (CLAUDE.md §41), restricted
    to the staff member's authorized client portfolio when one is assigned
    (CLAUDE.md-extension §22). Client users cannot access this consolidated
    screen."""
    repo = ClientRepository(db)
    out = []
    for client in repo.list_for_scope(allowed_client_ids=scope.client_ids):
        total, active = repo.portfolio_counts(client.id)
        out.append(
            ClientPortfolioOut(
                id=client.id,
                name=client.name,
                industry=client.industry,
                account_manager=client.account_manager,
                status=client.status,
                created_at=client.created_at,
                total_requests=total,
                active_requests=active,
            )
        )
    return out


@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: int,
    scope: TalentScope = Depends(require_staff_scope),
    db: Session = Depends(get_db),
) -> ClientOut:
    if scope.client_ids is not None and client_id not in scope.client_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    client = ClientRepository(db).get_by_id(client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    return client
