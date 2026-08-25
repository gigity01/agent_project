"""文档上传各阶段结构化运维事件记录模块。

职责说明：
- 提供 `DocumentUploadLogger` 类，详细记录上传开始、原始文件落盘、SHA-256 哈希计算、重复校验拦截、元数据入库、业务 HTTP 异常与非预期系统异常等事件。
- 保证敏感文本（API Key、Token 等）在日志记录时被自动遮蔽 (redact)。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config.settings import DOCUMENT_UPLOAD_LOG_DIR
from app.shared.observability.jsonl_writer import JsonlEventWriter
from app.shared.observability.correlation import DocumentOperationContext
from app.shared.observability.logger import DocumentStageLogger

if TYPE_CHECKING:
    from fastapi import HTTPException

    from app.modules.document.infrastructure.persistence.models.document import (
        Document,
    )


class DocumentUploadLogger(DocumentStageLogger):
    """文档上传阶段专用结构化日志记录器。"""

    def __init__(
        self,
        *,
        operation_context: DocumentOperationContext | None = None,
    ) -> None:
        """初始化上传日志记录器并绑定 upload 日志输出目录。

        参数:
            operation_context: 可选的操作关联上下文。
        """
        super().__init__(
            stage="upload",
            operation_context=operation_context,
            writer=JsonlEventWriter(
                log_dir=DOCUMENT_UPLOAD_LOG_DIR,
                file_prefix="upload",
            ),
        )

    def started(
        self,
        *,
        doc_code: str,
        kb_id: int,
        domain_code: str | None,
        business_scene: str | None,
        title: str,
        filename: str,
        source_type: str,
        saved_filename: str,
        created_by_actor_code: str,
    ) -> None:
        """记录文件开始上传并绑定本次任务业务上下文。

        参数:
            doc_code: 文档业务编号。
            kb_id: 知识库 ID。
            domain_code: 业务领域编码。
            business_scene: 业务场景编码。
            title: 文档标题。
            filename: 原始文件名。
            source_type: 文档扩展名源类型。
            saved_filename: 落盘存储文件名。
            created_by_actor_code: 操作人标识。
        """
        self.bind(
            doc_code=doc_code,
            kb_id=kb_id,
            domain_code=domain_code,
            business_scene=business_scene,
            source_type=source_type,
        )
        self.write(
            phase="execute",
            level="info",
            event="document_upload_started",
            message="源文档开始上传",
            title=title,
            filename=filename,
            saved_filename=saved_filename,
            created_by_actor_code=created_by_actor_code,
        )

    def raw_file_saved(
        self,
        *,
        doc_code: str,
        kb_id: int,
        source_uri: str,
        file_size: int,
    ) -> None:
        """记录原始文件成功分块写入本地存储。

        参数:
            doc_code: 文档编号。
            kb_id: 知识库 ID。
            source_uri: 本地存储路径 URI。
            file_size: 文件总大小（字节）。
        """
        self.write(
            phase="execute",
            level="info",
            event="document_upload_raw_file_saved",
            message="源文档已保存到目录当中",
            doc_code=doc_code,
            kb_id=kb_id,
            source_uri=source_uri,
            file_size=file_size,
        )

    def hash_calculated(
        self,
        *,
        doc_code: str,
        kb_id: int,
        content_hash: str,
    ) -> None:
        """记录文件 SHA-256 内容哈希计算完成。

        参数:
            doc_code: 文档编号。
            kb_id: 知识库 ID。
            content_hash: 文件 SHA-256 字符串。
        """
        self.write(
            phase="execute",
            level="info",
            event="document_upload_hash_calculated",
            message="源文档 hash 值已计算完成",
            doc_code=doc_code,
            kb_id=kb_id,
            content_hash=content_hash,
        )

    def duplicate_detected(
        self,
        *,
        doc_code: str,
        kb_id: int,
        content_hash: str,
        duplicated_document: Document,
    ) -> None:
        """记录因同知识库内内容哈希重复而被业务规则拒绝上传。

        参数:
            doc_code: 当前尝试上传的文档编号。
            kb_id: 知识库 ID。
            content_hash: 重复的内容哈希。
            duplicated_document: 已存在的重复文档 ORM 实例。
        """
        self.write(
            phase="finalize",
            level="warning",
            event="document_upload_duplicate_detected",
            message="检测到重复文档，上传被拒绝",
            doc_code=doc_code,
            kb_id=kb_id,
            content_hash=content_hash,
            duplicated_document_id=duplicated_document.id,
            duplicated_doc_code=duplicated_document.doc_code,
            outcome="rejected",
            document_created=False,
            status_after=None,
            diagnosis_hint=(
                "该失败属于业务规则拒绝，不是系统异常。"
                "请检查是否重复上传了相同内容的文档。"
            ),
        )

    def completed(self, *, document: Document) -> None:
        """记录文档记录成功持久化至数据库，状态为 uploaded。

        参数:
            document: 创建成功的 Document ORM 实例。
        """
        self.bind(
            document_id=document.id,
            doc_code=document.doc_code,
            kb_id=document.kb_id,
            domain_code=document.domain_code,
            business_scene=document.business_scene,
            source_type=document.source_type,
        )
        self.write(
            phase="finalize",
            level="info",
            event="document_upload_completed",
            message="源文档上传完成，Document 元数据已写入数据库",
            title=document.title,
            original_filename=document.original_filename,
            source_uri=document.source_uri,
            file_size=document.file_size,
            content_hash=document.content_hash,
            version=document.version,
            status_after=document.status,
            created_by_actor_code=document.created_by_actor_code,
        )

    def failed_by_http_exception(
        self,
        *,
        exc: HTTPException,
        phase: str,
        doc_code: str | None,
        kb_id: int,
        domain_code: str | None,
        business_scene: str | None,
        title: str,
        filename: str | None,
        source_type: str | None,
        source_uri: str | None,
        file_size: int,
        cleanup_success: bool,
    ) -> None:
        """记录由输入校验或业务规则引发的 HTTP 异常及残留文件清理结果。

        参数:
            exc: 捕获的 HTTPException。
            phase: 发生异常的阶段。
            doc_code: 文档编号。
            kb_id: 知识库 ID。
            domain_code: 领域编码。
            business_scene: 业务场景。
            title: 文档标题。
            filename: 文件名。
            source_type: 源类型。
            source_uri: 文件 URI。
            file_size: 文件大小。
            cleanup_success: 残留原件文件是否清理成功。
        """
        self.write(
            phase=phase,
            level="warning",
            event="document_upload_failed",
            message="源文档上传失败，业务校验未通过",
            doc_code=doc_code,
            kb_id=kb_id,
            domain_code=domain_code,
            business_scene=business_scene,
            title=title,
            filename=filename,
            source_type=source_type,
            source_uri=source_uri,
            file_size=file_size,
            error_type="HTTPException",
            error_message=self._redact_sensitive_text(str(exc.detail)),
            http_status=exc.status_code,
            outcome="rejected",
            document_created=False,
            status_after=None,
            cleanup_success=cleanup_success,
            diagnosis_hint=(
                "该失败通常由管理员输入或业务规则导致，请检查文件名、"
                "文件类型、文件大小、重复文档或请求参数"
            ),
        )

    def failed_by_unexpected_exception(
        self,
        *,
        exc: Exception,
        phase: str,
        doc_code: str | None,
        kb_id: int,
        domain_code: str | None,
        business_scene: str | None,
        title: str,
        filename: str | None,
        source_type: str | None,
        source_uri: str | None,
        file_size: int,
        cleanup_success: bool,
    ) -> None:
        """记录未预期系统异常导致的上传失败及尽力清理原件结果。

        参数:
            exc: 捕获的非预期异常。
            phase: 发生阶段。
            doc_code: 文档编号。
            kb_id: 知识库 ID。
            domain_code: 领域编码。
            business_scene: 业务场景。
            title: 标题。
            filename: 文件名。
            source_type: 源类型。
            source_uri: 文件 URI。
            file_size: 文件大小。
            cleanup_success: 残留文件清理是否成功。
        """
        self.write(
            phase=phase,
            level="error",
            event="document_upload_failed",
            message="源文档上传失败，发生系统异常，请联系管理员",
            doc_code=doc_code,
            kb_id=kb_id,
            domain_code=domain_code,
            business_scene=business_scene,
            title=title,
            filename=filename,
            source_type=source_type,
            source_uri=source_uri,
            file_size=file_size,
            outcome="error",
            document_created=False,
            status_after=None,
            cleanup_success=cleanup_success,
            diagnosis_hint="该失败属于系统异常，请联系上级管理员处理",
            **self.error_fields(exc),
        )
