"""Context Selection 与 Conversation 锁的结构化事件日志。"""

from typing import Any
from uuid import uuid4

from app.config.settings import CONTEXT_OBSERVABILITY_LOG_DIR
from app.shared.observability.jsonl_writer import JsonlEventWriter


class ContextEventLogger:
    """以非阻断 JSONL 事件暴露可聚合的 Context 指标字段。"""

    def __init__(self, writer: JsonlEventWriter | None = None) -> None:
        self._writer = writer or JsonlEventWriter(
            log_dir=CONTEXT_OBSERVABILITY_LOG_DIR,
            file_prefix="context",
        )

    def write(
        self,
        event: str,
        *,
        level: str = "info",
        **fields: Any,
    ) -> bool:
        payload = {
            "schema_version": 1,
            "event_id": uuid4().hex,
            "event": event,
            "subsystem": "context",
            "level": level,
            **fields,
        }
        try:
            return self._writer.write(payload)
        except Exception:
            return False
