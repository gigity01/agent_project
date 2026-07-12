"""记录文档上传各阶段结构化审计事件。"""

from fastapi import HTTPException

from app.models.document import Document
from main_config.settings import DOCUMENT_UPLOAD_LOG_DIR
from utils.times import now_ms
from core.observability.jsonl_event_writer import JsonlEventWriter
from app.constants.document_status import DocumentStatus

class DocumentUploadLogger:
    """聚合一次上传任务的耗时、阶段和统一日志字段。"""


    def __init__(self) -> None:
        """初始化上传计时器和按日写入的 JSONL 日志器。"""
        self.started_at_ms = now_ms()
        self.writer = JsonlEventWriter(
            log_dir=DOCUMENT_UPLOAD_LOG_DIR,
            file_prefix="upload",
        )
        self.stage = DocumentStatus.UPLOADED.value


    def _write(self, *, event: str, level: str, message: str, **fields) -> None:
        """将公共上传上下文字段与事件特有字段合并后写入日志。"""
        payload = {
            "event": event,
            "level": level,
            "message": message,
            "duration_ms": self.duration_ms,
            "stage": self.stage,
            **fields,
        }

        self.writer.write(payload)

    @property
    def duration_ms(self) -> int:
        """返回当前上传任务自创建日志器以来的耗时。"""
        return now_ms() - self.started_at_ms

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
        """记录文件开始上传时的业务上下文。"""
        self._write(
            level="info",
            event="document_upload_started",
            message="源文档开始上传",
            doc_code=doc_code,
            kb_id=kb_id,
            domain_code=domain_code,
            business_scene=business_scene,
            title=title,
            filename=filename,
            source_type=source_type,
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
        """记录原始文件成功写入本地存储的事件。"""
        self._write(

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
        """记录文件内容哈希计算完成的事件。"""
        self._write(

            level="info",
            event="document_upload_hash_calculated",
            message="源文档hash值已计算完成",
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
        """记录因同知识库内容重复而拒绝上传的业务事件。"""
        self._write(

            level="warning",
            event="document_upload_duplicate_detected",
            message="检测到重复文档，上传被拒绝",
            doc_code=doc_code,
            kb_id=kb_id,
            content_hash=content_hash,
            duplicated_document_id=duplicated_document.id,
            duplicated_doc_code=duplicated_document.doc_code,
            diagnosis_hint="该失败属于业务规则拒绝，不是系统异常。请检查是否重复上传了相同内容的文档。",
        )

    def completed(
            self,
            *,
            document: Document,
    ) -> None:
        """记录文档元数据持久化成功的完成事件。"""
        self._write(

            level="info",
            event="document_upload_completed",
            message="源文档上传完成，Document 元数据已写入数据库",
            document_id=document.id,
            doc_code=document.doc_code,
            kb_id=document.kb_id,
            domain_code=document.domain_code,
            business_scene=document.business_scene,
            title=document.title,
            original_filename=document.original_filename,
            source_type=document.source_type,
            source_uri=document.source_uri,
            file_size=document.file_size,
            content_hash=document.content_hash,
            version=document.version,
            status_after=document.status,
            created_by_actor_code=document.created_by_actor_code,
            duration_ms=self.duration_ms,
        )

    def failed_by_http_exception(
            self,
            *,
            exc: HTTPException,
            doc_code: str,
            kb_id: int,
            domain_code: str | None,
            business_scene: str | None,
            title: str,
            filename: str,
            source_type: str,
            source_uri: str,
            file_size: int,
            cleanup_success: bool,
    ) -> None:
        """记录由输入校验或业务规则导致的上传失败。"""
        self._write(

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
            status_code=exc.status_code,
            error_detail=exc.detail,
            cleanup_success=cleanup_success,
            diagnosis_hint="该失败通常由管理员输入或业务规则导致，请检查文件名、文件类型、文件大小、重复文档或请求参数",
        )

    def failed_by_unexpected_exception(
            self,
            *,
            exc: Exception,
            doc_code: str,
            kb_id: int,
            domain_code: str | None,
            business_scene: str | None,
            title: str,
            filename: str,
            source_type: str,
            source_uri: str,
            file_size: int,
            cleanup_success: bool,
    ) -> None:
        """记录未预期异常导致的上传失败及清理结果。"""
        self._write(

            level="exception",
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
            error_type=exc.__class__.__name__,
            error_message=str(exc),
            cleanup_success=cleanup_success,
            diagnosis_hint="该失败属于系统异常，请联系上级管理员处理",
        )
