"""文档生命周期各阶段共享的结构化事件基类模块。

职责说明：
- 提供 `DocumentStageLogger` 抽象基类，封装文档流水线各阶段的统一公共字段注入（`schema_version`、`event_id`、`workflow_id`、`operation_id`、`stage`、`duration_ms`、`status_before`、`status_after`）。
- 提供敏感信息过滤（API Key、Token、密码等敏感字符串遮蔽）与统一异常格式化工具方法。
"""

import re
from typing import Any
from uuid import uuid4

from app.shared.observability.jsonl_writer import JsonlEventWriter
from app.shared.observability.correlation import DocumentOperationContext
from app.shared.time import now_ms


class DocumentStageLogger:
    """文档处理流水线各阶段日志记录器的统一基类。

    为单次阶段操作提供链路追踪 ID、耗时计时、业务字段绑定与标准事件结构组装。
    """

    def __init__(
        self,
        *,
        stage: str,
        writer: JsonlEventWriter,
        document_id: int | None = None,
        operation_context: DocumentOperationContext | None = None,
    ) -> None:
        """初始化阶段日志记录器基类。

        参数:
            stage: 当前生命周期阶段（如 `upload`、`process`、`chunk`、`index`）。
            writer: JSONL 底层文件写入器。
            document_id: 文档 ID（若已知）。
            operation_context: 文档全链路操作上下文（若缺省则自动生成）。
        """
        self.stage = stage
        self.document_id = document_id
        self.operation_context = (
            operation_context or DocumentOperationContext.create()
        )
        self.started_at_ms = now_ms()
        self.writer = writer
        self.context: dict[str, Any] = {}

    @property
    def duration_ms(self) -> int:
        """返回自当前日志器初始化至此刻的累计耗时（毫秒）。

        返回:
            int: 累计毫秒数。
        """
        return now_ms() - self.started_at_ms

    def bind(self, **fields: Any) -> None:
        """绑定当前阶段后续所有日志事件共享的业务上下文（如 `doc_code`、`kb_id` 等）。

        参数:
            **fields: 待绑定的字段键值对（自动忽略值为 None 的项）。
        """
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
        """组装标准结构化 Schema v2 载荷并调用底层的 JSONL 写入器写入。

        参数:
            event: 具体事件名称（如 `document_chunk_completed`）。
            phase: 生命周期子阶段（`claim`、`execute`、`finalize`、`compensate`）。
            level: 日志级别（`info`、`warning`、`error`）。
            message: 人类可读的事件摘要说明。
            **fields: 附加事件专属数据字段。

        返回:
            bool: 写入成功返回 True。
        """
        payload = {
            **self.context,
            **fields,
            "schema_version": 2,
            "event_id": uuid4().hex,
            "workflow_id": self.operation_context.workflow_id,
            "operation_id": self.operation_context.operation_id,
            "parent_operation_id": (
                self.operation_context.parent_operation_id
            ),
            "attempt": self.operation_context.attempt,
            "event": event,
            "stage": self.stage,
            "phase": phase,
            "level": level,
            "message": message,
            "duration_ms": self.duration_ms,
            "document_id": self.document_id,
            "status_before": fields.get("status_before"),
            "status_after": fields.get("status_after"),
        }
        return self.writer.write(payload)

    @staticmethod
    def error_fields(error: Exception) -> dict[str, Any]:
        """从异常对象中提取脱敏后的错误类型、错误信息及 HTTP 状态码。

        参数:
            error: 异常实例。

        返回:
            dict[str, Any]: 包含 `error_type`、`error_message` 和可选 `http_status` 的字典。
        """
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
        """正则表达式遮蔽文本中常见的 API Key、Token、Authorization 认证头与 URL 密码。

        参数:
            value: 原始字符串。

        返回:
            str: 敏感信息替换为 `<redacted>` 后的安全字符串。
        """
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
