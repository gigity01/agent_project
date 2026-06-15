from sqlalchemy.orm import Session

from app.models.parent_block import ParentBlock


class ParentBlockRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, parent_block: ParentBlock) -> ParentBlock:
        self.db.add(parent_block)
        self.db.flush()
        return parent_block

    def delete_by_doc_id(self, doc_id: int) -> None:
        (
            self.db.query(ParentBlock)
            .filter(ParentBlock.doc_id == doc_id)
            .delete(synchronize_session=False)
        )