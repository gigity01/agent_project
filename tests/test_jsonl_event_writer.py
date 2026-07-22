"""JSONL Writer 的非阻断写入与输入隔离测试。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.observability.jsonl_event_writer import JsonlEventWriter


class JsonlEventWriterTest(unittest.TestCase):
    def test_write_adds_created_at_without_mutating_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            writer = JsonlEventWriter(Path(temp_dir), "events")
            event = {"event": "document_test"}

            self.assertTrue(writer.write(event))

            self.assertNotIn("created_at", event)
            log_path = next(Path(temp_dir).glob("events-*.jsonl"))
            payload = json.loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["event"], "document_test")
            self.assertIn("created_at", payload)

    def test_write_failure_returns_false_and_does_not_raise(self) -> None:
        writer = JsonlEventWriter(Path("unwritable"), "events")

        with mock.patch.object(
            Path,
            "mkdir",
            side_effect=OSError("read only"),
        ), mock.patch(
            "core.observability.jsonl_event_writer.logger.exception"
        ) as log_exception:
            result = writer.write({"event": "document_test"})

        self.assertFalse(result)
        log_exception.assert_called_once()


if __name__ == "__main__":
    unittest.main()
