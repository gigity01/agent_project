"""Context 路由选择与 Conversation 并发锁的结构化事件日志记录模块。

职责说明：
- 提供 `ContextEventLogger` 类，统一以非阻断的 JSONL 事件记录 Context Agent 路由判定、Conversation 分布式锁获取/释放及热资源队列变更事件。
- 支持日志分析器聚合分析路由命中率、降级频率与锁竞争耗时。
"""

from typing import Any
from uuid import uuid4

from app.config.settings import CONTEXT_OBSERVABILITY_LOG_DIR
from app.shared.observability.jsonl_writer import JsonlEventWriter


class ContextEventLogger:
    """非阻断式 Context 领域结构化事件日志记录器。"""

    def __init__(self, writer: JsonlEventWriter | None = None) -> None:
        """初始化 Context 日志记录器。

        参数:
            writer: 可选的 JSONL 写入器，缺省时自动使用 `CONTEXT_OBSERVABILITY_LOG_DIR`。
        """
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
        """写入单条 Context 子系统事件日志。

        参数:
            event: 事件名称（如 `context_route_decision`、`conversation_lock_acquired`）。
            level: 日志级别（`info`、`warning`、`error`）。
            **fields: 事件附加字段键值对。

        返回:
            bool: 写入成功返回 True，失败返回 False（不抛出异常阻断业务流程）。
        """
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
