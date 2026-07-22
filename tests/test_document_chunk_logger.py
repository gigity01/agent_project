"""文档切块阶段语义事件测试。"""

import unittest
from pathlib import Path
from types import SimpleNamespace

from core.observability.document_chunk_logger import DocumentChunkLogger


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
        chunk_source_type="md",
        cleaned_path=Path("cleaned.md"),
        status_before="processed",
    )


class DocumentChunkLoggerTest(unittest.TestCase):
    def test_build_and_finalize_events_report_chunk_counts(self) -> None:
        chunk_logger = DocumentChunkLogger(document_id=13)
        chunk_logger.writer = _MemoryWriter()
        context = _context()
        result = SimpleNamespace(
            chunks=SimpleNamespace(
                parents=[object(), object()],
                children_by_parent_index={0: [object()], 1: [object(), object()]},
            )
        )

        chunk_logger.claimed(context)
        chunk_logger.build_started(context, chunker="MarkdownChunker")
        chunk_logger.build_completed(result, chunker="MarkdownChunker")
        chunk_logger.completed(
            SimpleNamespace(parent_count=2, child_count=3)
        )

        events = chunk_logger.writer.events
        self.assertEqual(
            [event["event"] for event in events],
            [
                "document_chunk_claimed",
                "document_chunk_build_started",
                "document_chunk_build_completed",
                "document_chunk_completed",
            ],
        )
        self.assertEqual(events[2]["parent_count"], 2)
        self.assertEqual(events[2]["child_count"], 3)
        self.assertEqual(events[3]["phase"], "finalize")

    def test_execute_failure_records_execute_phase(self) -> None:
        chunk_logger = DocumentChunkLogger(document_id=13)
        chunk_logger.writer = _MemoryWriter()

        chunk_logger.failed(
            error=RuntimeError("chunker failed"),
            phase="execute",
            context=_context(),
        )

        event = chunk_logger.writer.events[0]
        self.assertEqual(event["phase"], "execute")
        self.assertEqual(event["status_after"], "failed")


if __name__ == "__main__":
    unittest.main()
