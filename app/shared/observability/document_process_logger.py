"""文档处理与清洗转换阶段结构化 JSONL 运维事件记录模块。

职责说明：
- 提供 `DocumentProcessLogger` 类，记录文档处理任务领取 (claim)、Docling 转换/清洗完成 (finalize) 与失败 (failed) 的事件。
- 保证 Process 阶段的 staging 临时文件操作与 active_operation_id 状态变更具备完整审计痕迹。
"""

from typing import Any

from app.config.settings import DOCUMENT_PROCESS_LOG_DIR
from app.modules.document.domain.enums import DocumentStatus
from app.shared.observability.jsonl_writer import JsonlEventWriter
from app.shared.observability.correlation import DocumentOperationContext
from app.shared.observability.logger import DocumentStageLogger


class DocumentProcessLogger(DocumentStageLogger):
    """文档处理与清洗阶段专用结构化日志记录器。"""

    def __init__(
        self,
        *,
        document_id: int | None = None,
        operation_context: DocumentOperationContext | None = None,
    ) -> None:
        """初始化文档处理日志记录器。

        参数:
            document_id: 可选的文档 ID。
            operation_context: 可选的文档操作关联上下文。
        """
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
        """绑定领取成功后得到的不可变文档快照上下文字段。

        参数:
            context: 领取成功的处理执行上下文。
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
        """记录处理权领取成功并提交 processing 状态。

        参数:
            context: 处理执行上下文。
        """
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
        """记录标准化文件登记完成并将文档状态推进到 processed。

        参数:
            processed_source_type: 清洗后的目标源类型。
            cleaned_uri: 清洗文本持久化 URI。
        """
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
        """记录领取、转换执行或产物登记阶段的失败事件。

        参数:
            error: 捕获的异常对象。
            phase: 失败阶段。
            context: 可选的处理上下文。
            state_updated: 是否已更新文档状态。
            status_before: 失败前状态。
            status_after: 失败后状态。
        """
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
