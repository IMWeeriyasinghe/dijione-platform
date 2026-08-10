from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import TalentScope, get_talent_scope
from app.db.session import get_db
from app.repositories.talent_request_repo import TalentRequestRepository
from app.repositories.user_repo import UserRepository
from app.schemas.document import DocumentCreate, DocumentOut
from app.services.document_service import DocumentService

router = APIRouter(prefix="/api/talent/requests/{request_id}/documents", tags=["talent-documents"])


def _ensure_request_in_scope(request_id: int, scope: TalentScope, db: Session):
    request = TalentRequestRepository(db).get_by_id(request_id, client_id=scope.client_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Talent request not found")
    return request


@router.get("", response_model=list[DocumentOut])
def list_documents(
    request_id: int,
    scope: TalentScope = Depends(get_talent_scope),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    _ensure_request_in_scope(request_id, scope, db)
    service = DocumentService(db)
    user_repo = UserRepository(db)
    documents = service.list_for_request(request_id)
    return [
        service.to_out(
            d, (user_repo.get_by_id(d.uploaded_by).full_name if user_repo.get_by_id(d.uploaded_by) else "")
        )
        for d in documents
    ]


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    request_id: int,
    payload: DocumentCreate,
    scope: TalentScope = Depends(get_talent_scope),
    db: Session = Depends(get_db),
) -> DocumentOut:
    _ensure_request_in_scope(request_id, scope, db)
    service = DocumentService(db)
    payload.talent_request_id = request_id
    document = service.upload_document(actor_id=scope.user.id, payload=payload)
    db.commit()
    db.refresh(document)
    return service.to_out(document, scope.user.full_name)
