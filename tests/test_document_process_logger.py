"""文档处理阶段统一事件字段测试。"""

import unittest
from types import SimpleNamespace

from app.shared.observability.document_process_logger import DocumentProcessLogger
from app.shared.observability.correlation import DocumentOperationContext


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
    def test_operation_id_is_stable_and_retry_gets_new_operation(self) -> None:
        first_context = DocumentOperationContext.create(
            workflow_id="workflow-1",
            operation_id="operation-1",
            attempt=1,
        )
        second_context = DocumentOperationContext.create(
            workflow_id="workflow-1",
            operation_id="operation-2",
            attempt=2,
        )
        first = DocumentProcessLogger(
            document_id=13,
            operation_context=first_context,
        )
        first.writer = _MemoryWriter()
        second = DocumentProcessLogger(
            document_id=13,
            operation_context=second_context,
        )
        second.writer = _MemoryWriter()

        first.claimed(_context())
        first.completed(processed_source_type="md", cleaned_uri="cleaned.md")

        operation_ids = {
            event["operation_id"] for event in first.writer.events
        }
        self.assertEqual(operation_ids, {"operation-1"})
        self.assertEqual(first.operation_context.workflow_id, "workflow-1")
        self.assertEqual(second.operation_context.workflow_id, "workflow-1")
        self.assertNotEqual(
            first.operation_context.operation_id,
            second.operation_context.operation_id,
        )
        self.assertEqual(second.operation_context.attempt, 2)
        self.assertTrue(
            all(event["stage"] == "process" for event in first.writer.events)
        )
        required_fields = {
            "workflow_id",
            "operation_id",
            "attempt",
            "document_id",
            "stage",
            "phase",
            "event",
            "status_before",
            "status_after",
            "duration_ms",
        }
        self.assertTrue(
            all(required_fields <= event.keys() for event in first.writer.events)
        )
        self.assertTrue(
            all(event["parent_operation_id"] is None for event in first.writer.events)
        )
        self.assertTrue(
            all("run_id" not in event for event in first.writer.events)
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
