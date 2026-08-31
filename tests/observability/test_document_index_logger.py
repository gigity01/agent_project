"""文档向量索引阶段批次事件、敏感信息脱敏与补偿日志（DocumentIndexLogger）测试。

核心业务不变量：
1. 向量批次度量与敏感信息保护：
   - 记录向量生成与 Qdrant upsert 的批次索引、分批大小、耗时与维度，严禁将原始 embedding 文本或 API Key 序列化落入日志。
2. 补偿事件结构化记录：
   - 记录补偿开始与完成时的删除 Point 数量及耗时。
"""

import json
import unittest
from types import SimpleNamespace

from app.shared.observability.document_index_logger import DocumentIndexLogger


class _MemoryWriter:
    """测试用内存日志写入器。"""
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: dict) -> bool:
        self.events.append(dict(event))
        return True


def _context():
    """构造测试用 IndexingContext 替身。"""
    return SimpleNamespace(
        document_id=13,
        doc_code="DOC_013",
        kb_id=1,
        domain_code="knowledge_ops",
        business_scene="document_pipeline",
        source_type="md",
        chunks=(object(), object()),
        pending_count=1,
        retry_count=1,
        status_before="failed",
    )


class DocumentIndexLoggerTest(unittest.TestCase):
    """验证 DocumentIndexLogger 的批次统计、敏感信息屏蔽与补偿追踪。"""
    def setUp(self) -> None:
        self.index_logger = DocumentIndexLogger(document_id=13)
        self.index_logger.writer = _MemoryWriter()

    def test_embedding_batch_logs_counts_and_dimension_not_payload(self) -> None:
        secret_text = "sensitive embedding text"
        api_key = "test-api-key-must-not-appear"
        vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

        self.index_logger.claimed(_context())
        started_at = self.index_logger.embedding_batch_started(
            batch_index=1,
            batch_size=2,
            embedding_model="text-embedding-v3",
        )
        self.index_logger.embedding_batch_completed(
            batch_index=1,
            input_count=2,
            vectors=vectors,
            started_at_ms=started_at,
        )

        event = self.index_logger.writer.events[-1]
        serialized = json.dumps(self.index_logger.writer.events)
        self.assertEqual(event["vector_count"], 2)
        self.assertEqual(event["vector_size"], 3)
        self.assertNotIn("vectors", event)
        self.assertNotIn("chunk_ids", serialized)
        self.assertNotIn("point_ids", serialized)
        self.assertNotIn(secret_text, serialized)
        self.assertNotIn(api_key, serialized)

    def test_compensation_success_and_failure_are_distinct_events(self) -> None:
        started_at = self.index_logger.compensation_started(
            confirmed_point_count=1,
            uncertain_point_count=1,
        )
        self.index_logger.compensation_completed(
            requested_point_count=2,
            started_at_ms=started_at,
        )
        self.index_logger.compensation_failed(
            error=RuntimeError("delete failed"),
            confirmed_point_count=1,
            uncertain_point_count=1,
            point_count=2,
            started_at_ms=started_at,
        )

        events = self.index_logger.writer.events
        self.assertEqual(events[0]["phase"], "compensate")
        self.assertEqual(events[1]["requested_point_count"], 2)
        self.assertNotIn("deleted_point_count", events[1])
        self.assertEqual(
            events[2]["event"],
            "document_index_compensation_failed",
        )
        self.assertNotIn("point_ids", json.dumps(events))

    def test_finalize_failure_records_confirmed_and_uncertain_counts(self) -> None:
        self.index_logger.failed(
            error=RuntimeError(
                "database finalize failed api_key=test-secret-value"
            ),
            phase="finalize",
            context=_context(),
            document_state_updated=False,
            chunk_state_updated_count=1,
            status_before="archived",
            status_after="archived",
            operation="qdrant_upsert",
            batch_index=3,
            batch_size=10,
            confirmed_point_count=2,
            uncertain_point_count=1,
        )

        event = self.index_logger.writer.events[0]
        self.assertEqual(event["phase"], "finalize")
        self.assertEqual(event["confirmed_point_count"], 2)
        self.assertEqual(event["uncertain_point_count"], 1)
        self.assertFalse(event["document_state_updated"])
        self.assertEqual(event["chunk_state_updated_count"], 1)
        self.assertEqual(event["status_after"], "archived")
        self.assertEqual(event["operation"], "qdrant_upsert")
        self.assertNotIn("test-secret-value", event["error_message"])
        self.assertIn("<redacted>", event["error_message"])


if __name__ == "__main__":
    unittest.main()
