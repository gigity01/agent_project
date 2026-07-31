"""文档生命周期各阶段共享的结构化事件模型。"""

import re
from typing import Any
from uuid import uuid4

from app.shared.observability.jsonl_writer import JsonlEventWriter
from app.shared.time import now_ms


class DocumentStageLogger:
    """为一次文档阶段调用提供稳定的 run_id 和统一公共字段。"""

    def __init__(
        self,
        *,
        stage: str,
        writer: JsonlEventWriter,
        document_id: int | None = None,
    ) -> None:
        self.stage = stage
        self.document_id = document_id
        self.run_id = uuid4().hex
        self.started_at_ms = now_ms()
        self.writer = writer
        self.context: dict[str, Any] = {}

    @property
    def duration_ms(self) -> int:
        """返回日志器创建至当前事件发生时的累计耗时。"""
        return now_ms() - self.started_at_ms

    def bind(self, **fields: Any) -> None:
        """绑定后续事件共享的非空文档业务上下文。"""
        document_id = fields.pop("document_id", None)
        if document_id is not None:
            self.document_id = document_id
        self.context.update(
            {
                key: value
                for key, value in fields.items()
                if value is not None
            }
        )

    def write(
        self,
        *,
        event: str,
        phase: str,
        level: str,
        message: str,
        **fields: Any,
    ) -> bool:
        """合并公共字段和事件字段，并交给非阻断 Writer 写入。"""
        payload = {
            **self.context,
            **fields,
            "schema_version": 1,
            "event_id": uuid4().hex,
            "run_id": self.run_id,
            "event": event,
            "stage": self.stage,
            "phase": phase,
            "level": level,
            "message": message,
            "duration_ms": self.duration_ms,
            "document_id": self.document_id,
        }
        return self.writer.write(payload)

    @staticmethod
    def error_fields(error: Exception) -> dict[str, Any]:
        """提取适用于 HTTPException 和普通异常的安全诊断字段。"""
        root_error = error.__cause__ or error
        fields: dict[str, Any] = {
            "error_type": type(root_error).__name__,
            "error_message": DocumentStageLogger._redact_sensitive_text(
                str(root_error)
            ),
        }
        http_status = getattr(error, "status_code", None)
        if http_status is not None:
            fields["http_status"] = http_status
        return fields

    @staticmethod
    def _redact_sensitive_text(value: str) -> str:
        """遮蔽异常文本中常见的认证字段和 URL 密码。"""
        redacted = re.sub(
            r"(?i)\b(api[_-]?key|token|authorization)\s*[:=]\s*"
            r"(?:bearer\s+)?[^\s,;]+",
            lambda match: f"{match.group(1)}=<redacted>",
            value,
        )
        return re.sub(
            r"(://[^\s:/@]+:)[^\s/@]+(@)",
            r"\1<redacted>\2",
            redacted,
        )
