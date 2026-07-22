"""记录文档切块领取、构建和登记事件。"""

from typing import Any

from app.constants.document_status import DocumentStatus
from core.observability.document_stage_logger import DocumentStageLogger
from core.observability.jsonl_event_writer import JsonlEventWriter
from main_config.settings import DOCUMENT_CHUNK_LOG_DIR


class DocumentChunkLogger(DocumentStageLogger):
    """提供切块阶段语义明确的结构化日志方法。"""

    def __init__(self, *, document_id: int | None = None) -> None:
        super().__init__(
            stage="chunk",
            document_id=document_id,
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
    ) -> None:
        if context is not None:
            self.bind_context(context)
        self.write(
            event="document_chunk_failed",
            phase=phase,
            level="error",
            message="文档切块失败",
            status_after=(
                DocumentStatus.FAILED.value if context is not None else None
            ),
            **self.error_fields(error),
        )
