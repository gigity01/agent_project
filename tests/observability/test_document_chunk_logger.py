"""文档切块阶段结构化语义事件（DocumentChunkLogger）测试。

核心业务不变量：
1. 阶段生命周期事件对齐：
   - 记录 `document_chunk_claimed`、`document_chunk_build_started`、`document_chunk_build_completed` 与 `document_chunk_completed` 事件。
   - 统计并上报父块数量、子块数量与切块器类型（MarkdownChunker, TextChunker, CsvChunker）。
"""

import unittest
from pathlib import Path
from types import SimpleNamespace

from app.shared.observability.document_chunk_logger import DocumentChunkLogger


class _MemoryWriter:
    """测试用内存日志写入器。"""
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: dict) -> bool:
        self.events.append(dict(event))
        return True


def _context():
    """构造测试用 ChunkingContext 替身。"""
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
    """验证 DocumentChunkLogger 的阶段事件上报与父子块数量统计。"""
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
            state_updated=True,
            status_before="chunking",
            status_after="failed",
        )

        event = chunk_logger.writer.events[0]
        self.assertEqual(event["phase"], "execute")
        self.assertTrue(event["state_updated"])
        self.assertEqual(event["status_after"], "failed")


if __name__ == "__main__":
    unittest.main()
