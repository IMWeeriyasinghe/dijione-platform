from sqlalchemy.orm import Session

from app.models.document import Document
from app.repositories.document_repo import DocumentRepository
from app.repositories.talent_request_repo import TalentRequestRepository
from app.schemas.document import DocumentCreate, DocumentOut
from app.services.audit_service import AuditService


class TalentRequestNotFoundError(Exception):
    pass


class DocumentService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = DocumentRepository(db)
        self.request_repo = TalentRequestRepository(db)
        self.audit = AuditService()

    def upload_document(self, *, actor_id: int, actor_name: str, payload: DocumentCreate) -> Document:
        request = self.request_repo.get_by_id(payload.talent_request_id, client_id=None)
        if request is None:
            raise TalentRequestNotFoundError(payload.talent_request_id)
        document = Document(
            talent_request_id=payload.talent_request_id,
            file_name=payload.file_name,
            category=payload.category,
            uploaded_by=actor_id,
            uploaded_by_name=actor_name,
            storage_reference=payload.storage_reference or f"local://demo-files/{payload.file_name}",
        )
        self.repo.add(document)
        self.audit.log(
            actor_id=actor_id,
            action="document.uploaded",
            entity_type="Document",
            entity_id=document.id,
            new_state={"file_name": document.file_name},
        )
        return document

    def list_for_request(self, request_id: int) -> list[Document]:
        return self.repo.list_for_request(request_id)

    def to_out(self, document: Document) -> DocumentOut:
        return DocumentOut(
            id=document.id,
            talent_request_id=document.talent_request_id,
            file_name=document.file_name,
            category=document.category,
            uploaded_by=document.uploaded_by,
            uploaded_by_name=document.uploaded_by_name,
            storage_reference=document.storage_reference,
            created_at=document.created_at,
        )
