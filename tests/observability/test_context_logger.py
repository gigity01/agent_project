"""Context 结构化事件日志测试。"""

import unittest

from app.shared.observability.context_logger import ContextEventLogger


class _Writer:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[dict] = []

    def write(self, event: dict) -> bool:
        if self.fail:
            raise OSError("log unavailable")
        self.events.append(dict(event))
        return True


class ContextEventLoggerTest(unittest.TestCase):
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
