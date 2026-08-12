from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, get_talent_scope
from app.db.session import get_db
from app.repositories.talent_request_repo import TalentRequestRepository
from app.repositories.user_repo import UserRepository
from app.schemas.message import MessageCreate, MessageOut
from app.services.message_service import MessageService

router = APIRouter(prefix="/api/talent/requests/{request_id}/messages", tags=["talent-messages"])


def _ensure_request_in_scope(request_id: int, scope: TalentScope, db: Session):
    request = TalentRequestRepository(db).get_by_id(
        request_id, client_id=scope.client_id, allowed_client_ids=scope.client_ids
    )
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talent request not found")
    return request


@router.get("", response_model=list[MessageOut])
def list_messages(
    request_id: int,
    scope: TalentScope = Depends(get_talent_scope),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    _ensure_request_in_scope(request_id, scope, db)
    service = MessageService(db)
    user_repo = UserRepository(db)
    messages = service.list_for_request(request_id)
    return [
        service.to_out(m, (user_repo.get_by_id(m.sender_id).full_name if user_repo.get_by_id(m.sender_id) else ""))
        for m in messages
    ]


@router.post("", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def create_message(
    request_id: int,
    payload: MessageCreate,
    scope: TalentScope = Depends(get_talent_scope),
    db: Session = Depends(get_db),
) -> MessageOut:
    _ensure_request_in_scope(request_id, scope, db)
    service = MessageService(db)
    message = service.send_message(
        talent_request_id=request_id, sender_id=scope.user.id, sender_role=scope.role, body=payload.body
    )
    db.commit()
    db.refresh(message)
    return service.to_out(message, scope.user.full_name)
