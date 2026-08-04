"""记录文档处理流程的结构化 JSONL 运维事件。"""

from typing import Any

from app.config.settings import DOCUMENT_PROCESS_LOG_DIR
from app.modules.document.domain.enums import DocumentStatus
from app.shared.observability.jsonl_writer import JsonlEventWriter
from app.shared.observability.correlation import DocumentOperationContext
from app.shared.observability.logger import DocumentStageLogger


class DocumentProcessLogger(DocumentStageLogger):
    """提供处理领取、完成和失败事件的稳定业务接口。"""

    def __init__(
        self,
        *,
        document_id: int | None = None,
        operation_context: DocumentOperationContext | None = None,
    ) -> None:
        super().__init__(
            stage="process",
            document_id=document_id,
            operation_context=operation_context,
            writer=JsonlEventWriter(
                log_dir=DOCUMENT_PROCESS_LOG_DIR,
                file_prefix="process",
            ),
        )

    def bind_context(self, context: Any) -> None:
        """绑定领取成功后得到的不可变文档快照。"""
        self.bind(
            document_id=context.document_id,
            doc_code=context.doc_code,
            kb_id=context.kb_id,
            domain_code=context.domain_code,
            business_scene=context.business_scene,
            source_type=context.source_type,
        )

    def claimed(self, context: Any) -> None:
        """记录处理权领取并提交 processing 状态。"""
        self.bind_context(context)
        self.write(
            event="document_process_claimed",
            phase="claim",
            level="info",
            message="文档处理任务领取完成",
            status_before=context.status_before,
            status_after=DocumentStatus.PROCESSING.value,
        )

    def completed(
        self,
        *,
        processed_source_type: str,
        cleaned_uri: str,
    ) -> None:
        """记录标准化文件登记完成并推进到 processed。"""
        self.write(
            event="document_process_completed",
            phase="finalize",
            level="info",
            message="文档处理完成，标准化产物已登记",
            processed_source_type=processed_source_type,
            cleaned_uri=cleaned_uri,
            status_before=DocumentStatus.PROCESSING.value,
            status_after=DocumentStatus.PROCESSED.value,
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
        """记录领取、执行或完成阶段失败。"""
        if context is not None:
            self.bind_context(context)
        self.write(
            event="document_process_failed",
            phase=phase,
            level="error",
            message="文档处理失败",
            state_updated=state_updated,
            status_before=status_before,
            status_after=status_after,
            **self.error_fields(error),
        )
