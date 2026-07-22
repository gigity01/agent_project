"""文档处理阶段统一事件字段测试。"""

import unittest
from types import SimpleNamespace

from core.observability.document_process_logger import DocumentProcessLogger


class _MemoryWriter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: dict) -> bool:
        self.events.append(dict(event))
        return True


def _context():
    return SimpleNamespace(
        document_id=13,
        doc_code="DOC_013",
        kb_id=1,
        domain_code="knowledge_ops",
        business_scene="document_pipeline",
        source_type="pdf",
        status_before="uploaded",
    )


class DocumentProcessLoggerTest(unittest.TestCase):
    def test_run_id_is_stable_per_task_and_unique_between_tasks(self) -> None:
        first = DocumentProcessLogger(document_id=13)
        first.writer = _MemoryWriter()
        second = DocumentProcessLogger(document_id=13)
        second.writer = _MemoryWriter()

        first.claimed(_context())
        first.completed(processed_source_type="md", cleaned_uri="cleaned.md")

        run_ids = {event["run_id"] for event in first.writer.events}
        self.assertEqual(len(run_ids), 1)
        self.assertNotEqual(first.run_id, second.run_id)
        self.assertTrue(
            all(event["stage"] == "process" for event in first.writer.events)
        )

    def test_claim_failure_contains_requested_document_and_phase(self) -> None:
        process_logger = DocumentProcessLogger(document_id=404)
        process_logger.writer = _MemoryWriter()
        error = RuntimeError("文档不存在")

        process_logger.failed(error=error, phase="claim", context=None)

        event = process_logger.writer.events[0]
        self.assertEqual(event["event"], "document_process_failed")
        self.assertEqual(event["phase"], "claim")
        self.assertEqual(event["document_id"], 404)
        self.assertEqual(event["error_type"], "RuntimeError")


if __name__ == "__main__":
    unittest.main()
