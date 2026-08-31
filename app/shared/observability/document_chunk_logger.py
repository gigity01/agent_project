"""文档切块阶段结构化事件日志记录模块。

职责说明：
- 提供 `DocumentChunkLogger` 类，记录切块任务领取 (claim)、构建开始/完成 (execute)、入库持久化 (finalize) 与失败 (failed) 各阶段的 JSONL 事件。
- 继承 `DocumentStageLogger`，自动附带文档关联上下文与耗时统计。
"""

from typing import Any

from app.config.settings import DOCUMENT_CHUNK_LOG_DIR
from app.modules.document.domain.enums import DocumentStatus
from app.shared.observability.jsonl_writer import JsonlEventWriter
from app.shared.observability.correlation import DocumentOperationContext
from app.shared.observability.logger import DocumentStageLogger


class DocumentChunkLogger(DocumentStageLogger):
    """文档切块阶段专用结构化日志记录器。"""

    def __init__(
        self,
        *,
        document_id: int | None = None,
        operation_context: DocumentOperationContext | None = None,
    ) -> None:
        """初始化切块日志记录器并绑定 chunk 日志输出目录。

        参数:
            document_id: 可选的文档 ID。
            operation_context: 可选的文档操作关联上下文。
        """
        super().__init__(
            stage="chunk",
            document_id=document_id,
            operation_context=operation_context,
            writer=JsonlEventWriter(
                log_dir=DOCUMENT_CHUNK_LOG_DIR,
                file_prefix="chunk",
            ),
        )

    def bind_context(self, context: Any) -> None:
        """绑定切块上下文对象（ClaimDocumentChunkContext）中的公共字段。

        参数:
            context: 领取成功的切块执行上下文。
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
        """记录切块任务领取成功并进入 chunking 状态。

        参数:
            context: 领取成功的切块执行上下文。
        """
        self.bind_context(context)
        self.write(
            event="document_chunk_claimed",
            phase="claim",
            level="info",
            message="文档切块任务领取完成",
            chunk_source_type=context.chunk_source_type,
            cleaned_uri=str(context.cleaned_path),
            status_before=context.status_before,
            status_after=DocumentStatus.CHUNKING.value,
        )

    def build_started(self, context: Any, *, chunker: str) -> None:
        """记录 Chunker 启动内存父子块拆分计算。

        参数:
            context: 切块执行上下文。
            chunker: 使用的 Chunker 实现类名称。
        """
        self.bind_context(context)
        self.write(
            event="document_chunk_build_started",
            phase="execute",
            level="info",
            message="Chunker 开始构建父子块",
            chunker=chunker,
            chunk_source_type=context.chunk_source_type,
            cleaned_uri=str(context.cleaned_path),
        )

    def build_completed(self, result: Any, *, chunker: str) -> None:
        """记录 Chunker 内存拆分计算完成及生成的父子块数量。

        参数:
            result: Chunker 输出的构建结果。
            chunker: Chunker 实现类名称。
        """
        parent_count = len(result.chunks.parents)
        child_count = sum(
            len(children)
            for children in result.chunks.children_by_parent_index.values()
        )
        self.write(
            event="document_chunk_build_completed",
            phase="execute",
            level="info",
            message="Chunker 父子块计算完成",
            chunker=chunker,
            parent_count=parent_count,
            child_count=child_count,
        )

    def completed(self, response: Any) -> None:
        """记录父子块批量写入数据库完成，文档状态推进为 chunked。

        参数:
            response: 切块用例响应对象。
        """
        self.write(
            event="document_chunk_completed",
            phase="finalize",
            level="info",
            message="文档父子块已写入数据库",
            parent_count=response.parent_count,
            child_count=response.child_count,
            status_before=DocumentStatus.CHUNKING.value,
            status_after=DocumentStatus.CHUNKED.value,
        )

    def failed(
        self,
        *,
        error: Exception,
        phase: str,
        context: Any | None = None,
        state_updated: bool = False,
        status_before: str | None = None,
        status_after: str | None = None,
    ) -> None:
        """记录切块流程在指定阶段失败的详细错误信息与状态转移。

        参数:
            error: 捕获的异常对象。
            phase: 发生失败的阶段（`claim`、`execute`、`finalize`）。
            context: 可选的切块上下文。
            state_updated: 文档状态是否已被更新为 failed。
            status_before: 失败前状态。
            status_after: 失败后状态。
        """
        if context is not None:
            self.bind_context(context)
        self.write(
            event="document_chunk_failed",
            phase=phase,
            level="error",
            message="文档切块失败",
            state_updated=state_updated,
            status_before=status_before,
            status_after=status_after,
            **self.error_fields(error),
        )
