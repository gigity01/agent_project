"""记录文档切块领取、构建和登记事件。"""

from typing import Any

from app.config.settings import DOCUMENT_CHUNK_LOG_DIR
from app.modules.document.domain.enums import DocumentStatus
from app.shared.observability.jsonl_writer import JsonlEventWriter
from app.shared.observability.correlation import DocumentOperationContext
from app.shared.observability.logger import DocumentStageLogger


class DocumentChunkLogger(DocumentStageLogger):
    """提供切块阶段语义明确的结构化日志方法。"""

    def __init__(
        self,
        *,
        document_id: int | None = None,
        operation_context: DocumentOperationContext | None = None,
    ) -> None:
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
