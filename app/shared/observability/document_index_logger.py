"""记录文档向量索引、批次写入和补偿事件。"""

from typing import Any

from app.config.settings import DOCUMENT_INDEX_LOG_DIR
from app.modules.document.domain.enums import DocumentStatus
from app.shared.observability.jsonl_writer import JsonlEventWriter
from app.shared.observability.correlation import DocumentOperationContext
from app.shared.observability.logger import DocumentStageLogger
from app.shared.time import now_ms


class DocumentIndexLogger(DocumentStageLogger):
    """提供索引阶段跨 MySQL、Embedding 和 Qdrant 的诊断事件。"""

    def __init__(
        self,
        *,
        document_id: int | None = None,
        operation_context: DocumentOperationContext | None = None,
    ) -> None:
        super().__init__(
            stage="index",
            document_id=document_id,
            operation_context=operation_context,
            writer=JsonlEventWriter(
                log_dir=DOCUMENT_INDEX_LOG_DIR,
                file_prefix="index",
            ),
        )

    def bind_context(self, context: Any) -> None:
        self.bind(
            document_id=context.document_id,
            doc_code=context.doc_code,
            kb_id=context.kb_id,
            domain_code=context.domain_code,
            business_scene=context.business_scene,
            source_type=context.source_type,
        )

    def claimed(self, context: Any) -> None:
        self.bind_context(context)
        self.write(
            event="document_index_claimed",
            phase="claim",
            level="info",
            message="文档向量索引任务领取完成",
            chunk_count=len(context.chunks),
            pending_count=context.pending_count,
            retry_count=context.retry_count,
            status_before=context.status_before,
            status_after=DocumentStatus.INDEXING.value,
        )

    def collection_ready(
        self,
        *,
        collection_name: str | None,
        vector_size: int,
    ) -> None:
        self.write(
            event="document_index_collection_ready",
            phase="execute",
            level="info",
            message="Qdrant Collection 检查完成",
            collection_name=collection_name,
            vector_size=vector_size,
        )

    def embedding_batch_started(
        self,
        *,
        batch_index: int,
        batch_size: int,
        embedding_model: str,
    ) -> int:
        self.write(
            event="document_index_embedding_batch_started",
            phase="execute",
            level="info",
            message="Embedding 批次开始生成",
            batch_index=batch_index,
            batch_size=batch_size,
            embedding_model=embedding_model,
        )
        return now_ms()

    def embedding_batch_completed(
        self,
        *,
        batch_index: int,
        input_count: int,
        vectors: list[list[float]],
        started_at_ms: int,
    ) -> None:
        self.write(
            event="document_index_embedding_batch_completed",
            phase="execute",
            level="info",
            message="Embedding 批次生成完成",
            batch_index=batch_index,
            input_count=input_count,
            vector_count=len(vectors),
            vector_size=len(vectors[0]) if vectors else 0,
            batch_duration_ms=now_ms() - started_at_ms,
        )

    def qdrant_batch_completed(
        self,
        *,
        batch_index: int,
        point_count: int,
        started_at_ms: int,
    ) -> None:
        self.write(
            event="document_index_qdrant_batch_completed",
            phase="execute",
            level="info",
            message="Qdrant 批次写入完成",
            batch_index=batch_index,
            point_count=point_count,
            batch_duration_ms=now_ms() - started_at_ms,
        )

    def completed(self, response: Any) -> None:
        self.write(
            event="document_index_completed",
            phase="finalize",
            level="info",
            message="文档向量索引完成",
            total_chunks=response.total_chunks,
            indexed_chunks=response.indexed_chunks,
            status_before=DocumentStatus.INDEXING.value,
            status_after=DocumentStatus.INDEXED.value,
        )

    def failed(
        self,
        *,
        error: Exception,
        phase: str,
        context: Any | None,
        document_state_updated: bool = False,
        chunk_state_updated_count: int = 0,
        status_before: str | None = None,
        status_after: str | None = None,
        operation: str | None = None,
        batch_index: int | None = None,
        batch_size: int | None = None,
        confirmed_point_count: int = 0,
        uncertain_point_count: int = 0,
    ) -> None:
        if context is not None:
            self.bind_context(context)
        self.write(
            event="document_index_failed",
            phase=phase,
            level="error",
            message="文档向量索引失败",
            operation=operation,
            batch_index=batch_index,
            batch_size=batch_size,
            confirmed_point_count=confirmed_point_count,
            uncertain_point_count=uncertain_point_count,
            document_state_updated=document_state_updated,
            chunk_state_updated_count=chunk_state_updated_count,
            status_before=status_before,
            status_after=status_after,
            **self.error_fields(error),
        )

    def compensation_started(
        self,
        *,
        confirmed_point_count: int,
        uncertain_point_count: int,
    ) -> int:
        self.write(
            event="document_index_compensation_started",
            phase="compensate",
            level="warning",
            message="Qdrant Point 补偿删除开始",
            confirmed_point_count=confirmed_point_count,
            uncertain_point_count=uncertain_point_count,
        )
        return now_ms()

    def compensation_completed(
        self,
        *,
        requested_point_count: int,
        started_at_ms: int,
    ) -> None:
        self.write(
            event="document_index_compensation_completed",
            phase="compensate",
            level="info",
            message="Qdrant Point 补偿删除完成",
            requested_point_count=requested_point_count,
            batch_duration_ms=now_ms() - started_at_ms,
        )

    def compensation_failed(
        self,
        *,
        error: Exception,
        confirmed_point_count: int,
        uncertain_point_count: int,
        point_count: int,
        started_at_ms: int,
    ) -> None:
        self.write(
            event="document_index_compensation_failed",
            phase="compensate",
            level="error",
            message="Qdrant Point 补偿删除失败",
            confirmed_point_count=confirmed_point_count,
            uncertain_point_count=uncertain_point_count,
            point_count=point_count,
            batch_duration_ms=now_ms() - started_at_ms,
            **self.error_fields(error),
        )
