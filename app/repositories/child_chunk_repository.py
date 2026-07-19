"""子块 ORM 模型的持久化和向量索引状态管理。"""

from collections.abc import Iterable
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

    def create_many(self, child_chunks: list[ChildChunk]) -> list[ChildChunk]:
        """批量加入子块并统一 flush；事务提交仍由调用方负责。"""
        if not child_chunks:
            return []

        self.db.add_all(child_chunks)
        self.db.flush()
        return child_chunks

    def delete_by_doc_id(self, doc_id: int) -> None:
        """删除指定文档的全部子块，不在此处提交事务。"""
        (
            self.db.query(ChildChunk)
            .filter(ChildChunk.doc_id == doc_id)
            .delete(synchronize_session=False)
        )

    def exists_by_doc_id(self, doc_id: int) -> bool:
        """判断文档是否仍有 active 子块，不改变任何持久化状态。"""
        return (
            self.db.query(ChildChunk.id)
            .filter(
                ChildChunk.doc_id == doc_id,
                ChildChunk.status == "active",
            )
            .first()
            is not None
        )

    def exists_by_doc_id_and_vector_status(
        self,
        doc_id: int,
        vector_status: str,
    ) -> bool:
        """判断文档是否存在指定向量状态的 active 子块。"""
        return (
            self.db.query(ChildChunk.id)
            .filter(
                ChildChunk.doc_id == doc_id,
                ChildChunk.status == "active",
                ChildChunk.vector_status == vector_status,
            )
            .first()
            is not None
        )

    def count_active_not_indexed_by_doc_id(self, doc_id: int) -> int:
        """统计文档中尚未完成向量索引的 active 子块。"""
        return (
            self.db.query(ChildChunk.id)
            .filter(
                ChildChunk.doc_id == doc_id,
                ChildChunk.status == "active",
                ChildChunk.vector_status != "indexed",
            )
            .count()
        )

    def list_indexable_by_doc_id(
        self,
        doc_id: int,
        statuses: set[str],
    ) -> list[ChildChunk]:
        """稳定返回指定文档中处于可领取向量状态的 active 子块。"""
        if not statuses:
            return []

        return (
            self.db.query(ChildChunk)
            .filter(
                ChildChunk.doc_id == doc_id,
                ChildChunk.status == "active",
                ChildChunk.vector_status.in_(statuses),
            )
            .order_by(
                ChildChunk.parent_id.asc(),
                ChildChunk.chunk_index.asc(),
            )
            .all()
        )

    def list_by_ids_for_update(
        self,
        doc_id: int,
        chunk_ids: Iterable[int],
    ) -> list[ChildChunk]:
        """按主键升序锁定文档内的本次索引子块，直至事务结束。"""
        ordered_ids = sorted(set(chunk_ids))
        if not ordered_ids:
            return []

        return (
            self.db.query(ChildChunk)
            .filter(
                ChildChunk.doc_id == doc_id,
                ChildChunk.id.in_(ordered_ids),
            )
            .order_by(ChildChunk.id)
            .with_for_update()
            .all()
        )

    def mark_indexing(self, chunks: list[ChildChunk]) -> None:
        """将本批子块切换为 indexing 状态。

        调用方需在发起外部 Embedding 请求前提交该状态，以便进程中断后能识别
        已离开 pending 队列、需要人工或任务系统补偿的批次。
        """
        for chunk in chunks:
            chunk.vector_status = "indexing"

        self.db.flush()

    def mark_indexed_many(self, chunks: list[ChildChunk]) -> None:
        """批量记录稳定 Point ID，并把本次子块统一标为 indexed。"""
        indexed_at = datetime.now()
        for chunk in chunks:
            chunk.vector_status = "indexed"
            chunk.qdrant_point_id = str(chunk.id)
            chunk.indexed_at = indexed_at

        self.db.flush()

    def mark_failed(self, chunks: list[ChildChunk]) -> None:
        """仅把仍处于 indexing 的本次子块标记为 failed。"""
        for chunk in chunks:
            if chunk.vector_status == "indexing":
                chunk.vector_status = "failed"

        self.db.flush()
