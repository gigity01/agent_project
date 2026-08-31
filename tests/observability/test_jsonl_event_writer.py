"""JSONL 结构化日志写入器（JsonlEventWriter）单元测试。

核心业务不变量：
1. 入参不可变性与 UTC 日期分文件：
   - 写入时追加 `created_at` 字段而不改变原始入参字典；按 UTC 日期归档至 `events-YYYY-MM-DD.jsonl` 文件。
2. 非阻断故障安全（Non-blocking Failure Handling）：
   - 文件系统只读或 I/O 错误时记录异常并返回 False，绝不向外冒泡异常破坏主业务流程。
"""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from app.shared.observability.jsonl_writer import JsonlEventWriter


class JsonlEventWriterTest(unittest.TestCase):
    """验证 JsonlEventWriter 的不可变写入、日期切分与异常安全。"""
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
            "app.shared.observability.jsonl_writer.logger.exception"
        ) as log_exception:
            result = writer.write({"event": "document_test"})

        self.assertFalse(result)
        log_exception.assert_called_once()

    def test_write_appends_complete_line_once_and_uses_utc_date(self) -> None:
        writer = JsonlEventWriter(Path("logs"), "events")
        opened_file = mock.mock_open()
        fixed_now = datetime(2026, 7, 22, 23, 59, tzinfo=timezone.utc)

        with mock.patch(
            "app.shared.observability.jsonl_writer.datetime"
        ) as datetime_mock:
            datetime_mock.now.return_value = fixed_now
            datetime_mock.side_effect = datetime
            self.assertEqual(
                writer._get_log_path().name,
                "events-2026-07-22.jsonl",
            )

        with mock.patch.object(Path, "mkdir"), mock.patch.object(
            Path,
            "open",
            opened_file,
        ):
            result = writer.write({"event": "document_test"})

        self.assertTrue(result)
        opened_file().write.assert_called_once()
        self.assertTrue(opened_file().write.call_args.args[0].endswith("\n"))


if __name__ == "__main__":
    unittest.main()
