from sqlalchemy.orm import Session

from app.models.document import Document


class DocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, document: Document) -> Document:
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def get_by_id(self, document_id: int) :
        return (
            self.db.query(Document)
            .filter(Document.id == document_id)
            .first()
        )

    def get_by_hash_in_kb(
            self,
            kb_id: int,
            content_hash: str,
    ) :
        return (
            self.db.query(Document)
            .filter(
                Document.kb_id == kb_id,
                Document.content_hash == content_hash,
                Document.status.notin_(["deleted", "archived", "replaced"]),
            )
            .first()
        )

    def update_status(
            self,
            document: Document,
            status: str,
    ) -> Document:
        document.status = status
        self.db.commit()
        self.db.refresh(document)
        return document

    def update_cleaned_uri(
            self,
            document: Document,
            cleaned_uri: str,
            status: str = "active",
    ) -> Document:
        document.cleaned_uri = cleaned_uri
        document.status = status
        self.db.commit()
        self.db.refresh(document)
        return document
