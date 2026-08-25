"""文档向量索引阶段结构化事件日志记录模块。

职责说明：
- 提供 `DocumentIndexLogger` 类，记录向量索引任务领取、Qdrant Collection 就绪、DashScope Embedding 批次生成、Qdrant 批次写入、完成、失败及补偿回滚删除等事件。
- 支持诊断跨 MySQL、DashScope 与 Qdrant 的分布式三阶段调用与不一致修复过程。
"""

from typing import Any

from app.config.settings import DOCUMENT_INDEX_LOG_DIR
from app.modules.document.domain.enums import DocumentStatus
from app.shared.observability.jsonl_writer import JsonlEventWriter
from app.shared.observability.correlation import DocumentOperationContext
from app.shared.observability.logger import DocumentStageLogger
from app.shared.time import now_ms


class DocumentIndexLogger(DocumentStageLogger):
    """文档向量索引阶段专用结构化日志记录器。"""

    def __init__(
        self,
        *,
        document_id: int | None = None,
        operation_context: DocumentOperationContext | None = None,
    ) -> None:
        """初始化向量索引日志记录器。

        参数:
            document_id: 可选的文档 ID。
            operation_context: 可选的文档操作关联上下文。
        """
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
        """绑定索引上下文对象（ClaimDocumentIndexContext）中的公共字段。

        参数:
            context: 领取成功的索引执行上下文。
        """
        self.bind(
            document_id=context.document_id,
            doc_code=context.doc_code,
            kb_id=context.kb_id,
            domain_code=context.domain_code,
            business_scene=context.business_scene,
            source_type=context.source_type,
        )

    def claimed(self, context: Any) -> None:
        """记录索引任务领取成功并推进 Document/Chunk 到 indexing 状态。

        参数:
            context: 领取成功的索引执行上下文。
        """
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
        """记录 Qdrant Collection 状态与向量维度检查通过。

        参数:
            collection_name: Collection 名称。
            vector_size: 向量维度大小。
        """
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
        """记录单个 Embedding 批次调用开始，并返回起始毫秒时间戳。

        参数:
            batch_index: 批次索引（从 0 开始）。
            batch_size: 本批子块数量。
            embedding_model: 调用的 Embedding 模型名。

        返回:
            int: 批次开始的毫秒时间戳。
        """
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
        """记录单个 Embedding 批次向量生成成功与耗时。

        参数:
            batch_index: 批次索引。
            input_count: 输入文本数量。
            vectors: 生成的向量数组列表。
            started_at_ms: 批次开始毫秒时间戳。
        """
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
        """记录单个 Qdrant 批次 Points upsert 写入成功。

        参数:
            batch_index: 批次索引。
            point_count: 写入的 Point 数量。
            started_at_ms: 批次开始毫秒时间戳。
        """
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
        """记录所有子块向量写入与数据库状态更新完成，状态进入 indexed。

        参数:
            response: 索引响应对象。
        """
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
        """记录索引流程失败的详细错误、批次信息与 Qdrant Point 不确定性统计。

        参数:
            error: 异常对象。
            phase: 失败阶段。
            context: 索引上下文。
            document_state_updated: 文档状态是否已更新。
            chunk_state_updated_count: 更新失败状态的 chunk 数量。
            status_before: 失败前状态。
            status_after: 失败后状态。
            operation: 失败的操作类型。
            batch_index: 失败的批次索引。
            batch_size: 失败批次大小。
            confirmed_point_count: 已确认写入的 Point 数量。
            uncertain_point_count: 状态不确定的 Point 数量。
        """
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
        """记录 Qdrant Point 补偿删除回滚启动。

        参数:
            confirmed_point_count: 已确认 Point 数量。
            uncertain_point_count: 不确定 Point 数量。

        返回:
            int: 补偿开始毫秒时间戳。
        """
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
        """记录 Qdrant Point 补偿删除成功。

        参数:
            requested_point_count: 请求删除的 Point 数量。
            started_at_ms: 补偿开始毫秒时间戳。
        """
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
        """记录 Qdrant Point 补偿删除失败（保留所有权禁止接管）。

        参数:
            error: 异常对象。
            confirmed_point_count: 确认 Point 数。
            uncertain_point_count: 不确定 Point 数。
            point_count: 总 Point 数。
            started_at_ms: 开始时间戳。
        """
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
