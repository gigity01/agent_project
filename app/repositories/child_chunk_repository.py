# app/repositories/child_chunk_repository.py

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.child_chunk import ChildChunk



class ChildChunkRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, child_chunk: ChildChunk) -> ChildChunk:
        self.db.add(child_chunk)
        self.db.flush()
        return child_chunk

    def delete_by_doc_id(self, doc_id: int) -> None:
        (
            self.db.query(ChildChunk)
            .filter(ChildChunk.doc_id == doc_id)
            .delete(synchronize_session=False)
        )

    def list_pending_by_doc_id(self, doc_id: int):
        return (
            self.db.query(ChildChunk)
            .filter(
                ChildChunk.doc_id == doc_id,
                ChildChunk.status == "active",
                ChildChunk.vector_status == "pending",
            )
            .order_by(
                ChildChunk.parent_id.asc(),
                ChildChunk.chunk_index.asc(),
            )
            .all()
        )

    def mark_indexing(self, chunks: list[ChildChunk]) -> None:
        for chunk in chunks:
            chunk.vector_status = "indexing"

        self.db.flush()

    def mark_indexed(
        self,
        chunk: ChildChunk,
        qdrant_point_id: str,
    ) -> None:
        chunk.vector_status = "indexed"
        chunk.qdrant_point_id = qdrant_point_id
        chunk.indexed_at = datetime.now()

        self.db.flush()

    def mark_failed_by_ids(self, chunk_ids: list[int]) -> None:
        if not chunk_ids:
            return

        (
            self.db.query(ChildChunk)
            .filter(ChildChunk.id.in_(chunk_ids))
            .update(
                {ChildChunk.vector_status: "failed"},
                synchronize_session=False,
            )
        )

        self.db.flush()