"""记录文档处理流程的结构化 JSONL 审计事件。"""

import sys
from pathlib import Path

# Add project root to sys.path so that imports like "main_utils.times" and "core.*" resolve correctly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from typing import Any

from core.observability.jsonl_event_writer import JsonlEventWriter
from main_config.settings import DOCUMENT_PROCESS_LOG_DIR
from main_utils.times import now_ms
from app.services.document_upload_service import save_uploaded_document


class DocumentProcessLogger:
    """聚合一次文档处理任务的事件、耗时和诊断字段。"""

    def __init__(self) -> None:
        """初始化处理计时器和按日切分的 JSONL 写入器。"""
        self.started_at_ms = now_ms()
        self.writer = JsonlEventWriter(
            log_dir=DOCUMENT_PROCESS_LOG_DIR,
            file_prefix="process",
        )

    def started(self, *, document_id: int, doc_code: str, source_type: str) -> None:
        """记录文档开始进入处理阶段。"""
        self._write(
            event="document_process_started",
            level="info",
            document_id=document_id,
            doc_code=doc_code,
            source_type=source_type,
        )

    def completed(
        self,
        *,
        document_id: int,
        doc_code: str,
        processed_source_type: str,
        cleaned_uri: str,
    ) -> None:
        """记录文档清洗完成并可进入切块阶段。"""
        self._write(
            event="document_process_completed",
            level="info",
            document_id=document_id,
            doc_code=doc_code,
            processed_source_type=processed_source_type,
            cleaned_uri=cleaned_uri,
        )

    def failed(
        self,
        *,
        document_id: int,
        doc_code: str,
        error: Exception,
    ) -> None:
        """记录服务端诊断信息，客户端仅接收通用错误。"""
        self._write(
            event="document_process_failed",
            level="exception",
            document_id=document_id,
            doc_code=doc_code,
            error_type=type(error).__name__,
            error_message=str(error),
        )

    def _write(self, *, event: str, level: str, **fields: Any) -> None:
        """写入包含处理耗时的统一事件格式。"""
        self.writer.write(
            {
                "event": event,
                "level": level,
                "duration_ms": now_ms() - self.started_at_ms,
                **fields,
            }
        )
