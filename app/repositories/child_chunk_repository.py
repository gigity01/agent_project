"""子块 ORM 模型的持久化和向量索引状态管理。"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.child_chunk import ChildChunk



class ChildChunkRepository:
    """封装子块创建、重建清理与索引状态转换。"""
    def __init__(self, db: Session):
        self.db = db

    def create(self, child_chunk: ChildChunk) -> ChildChunk:
        """加入会话并 flush，使调用方可继续使用新子块主键。"""
        self.db.add(child_chunk)
        self.db.flush()
        return child_chunk

    def delete_by_doc_id(self, doc_id: int) -> None:
        """删除指定文档的全部子块，不在此处提交事务。"""
        (
            self.db.query(ChildChunk)
            .filter(ChildChunk.doc_id == doc_id)
            .delete(synchronize_session=False)
        )

    def list_pending_by_doc_id(self, doc_id: int):
        """按父块和块序号稳定返回等待向量化的有效子块。"""
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
        """将本批子块切换为 indexing 状态。"""
        for chunk in chunks:
            chunk.vector_status = "indexing"

        self.db.flush()

    def mark_indexed(
        self,
        chunk: ChildChunk,
        qdrant_point_id: str,
    ) -> None:
        """记录 Qdrant point 标识并将子块标记为 indexed。"""
        chunk.vector_status = "indexed"
        chunk.qdrant_point_id = qdrant_point_id
        chunk.indexed_at = datetime.now()

        self.db.flush()

    def mark_failed_by_ids(self, chunk_ids: list[int]) -> None:
        """将指定批次标记为 failed，供人工或任务重试。"""
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
