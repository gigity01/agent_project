"""记录文档处理流程的结构化 JSONL 运维事件。"""

from typing import Any

from app.constants.document_status import DocumentStatus
from core.observability.document_stage_logger import DocumentStageLogger
from core.observability.jsonl_event_writer import JsonlEventWriter
from main_config.settings import DOCUMENT_PROCESS_LOG_DIR


class DocumentProcessLogger(DocumentStageLogger):
    """提供处理领取、完成和失败事件的稳定业务接口。"""

    def __init__(self, *, document_id: int | None = None) -> None:
        super().__init__(
            stage="process",
            document_id=document_id,
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
    ) -> None:
        """记录领取、执行或完成阶段失败。"""
        if context is not None:
            self.bind_context(context)
        self.write(
            event="document_process_failed",
            phase=phase,
            level="error",
            message="文档处理失败",
            status_before=(
                context.status_before
                if phase == "claim" and context is not None
                else DocumentStatus.PROCESSING.value
                if context is not None
                else None
            ),
            status_after=(
                DocumentStatus.FAILED.value if context is not None else None
            ),
            **self.error_fields(error),
        )
