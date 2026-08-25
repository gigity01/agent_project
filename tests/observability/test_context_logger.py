"""Context 子系统结构化事件日志（ContextEventLogger）封包与容错测试。

核心业务不变量：
1. 稳定信封（Standard Envelope）：
   - 所有事件统一注入 `schema_version: 1`、唯一 `event_id`、`subsystem: 'context'` 及当前时间戳。
2. 故障非阻断（Fault-tolerant / Non-blocking）：
   - 日志写入器发生任何 I/O 或系统异常时，返回 False 并安全吞没异常，绝不阻塞 Context 核心路由与完成流转。
"""

import unittest

from app.shared.observability.context_logger import ContextEventLogger


class _Writer:
    """测试用日志写入器替身，支持注入异常。"""
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[dict] = []

    def write(self, event: dict) -> bool:
        if self.fail:
            raise OSError("log unavailable")
        self.events.append(dict(event))
        return True


class ContextEventLoggerTest(unittest.TestCase):
    """验证 ContextEventLogger 的信封生成与写入容错。"""
    def test_adds_stable_envelope_to_metric_fields(self) -> None:
        writer = _Writer()
        logger = ContextEventLogger(writer)

        written = logger.write(
            "context_selection_completed",
            conversation_id="conversation-1",
            context_selection_selected_count=2,
        )

        self.assertTrue(written)
        event = writer.events[0]
        self.assertEqual(event["schema_version"], 1)
        self.assertTrue(event["event_id"])
        self.assertEqual(event["subsystem"], "context")
        self.assertEqual(event["context_selection_selected_count"], 2)

    def test_writer_failure_never_blocks_context_flow(self) -> None:
        logger = ContextEventLogger(_Writer(fail=True))

        self.assertFalse(logger.write("context_route_lock_expired"))


if __name__ == "__main__":
    unittest.main()
