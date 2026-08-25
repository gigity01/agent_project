"""文档流水线四个独立阶段（Upload, Process, Chunk, Index）全链路关联模型（DocumentOperationContext）测试。

核心业务不变量（遵循 AGENTS.md 规范）：
1. 共享 Workflow 与独立 Operation：
   - 同一个文档的处理全生命周期共享相同的 `workflow_id`。
   - 每个独立步骤拥有各自独立的 `operation_id`，下游步骤可通过 `parent_operation_id` 显式链接上游步骤（如 Process 链接 Upload）。
"""

from __future__ import annotations

import unittest

from app.shared.observability.correlation import DocumentOperationContext
from app.shared.observability.document_chunk_logger import DocumentChunkLogger
from app.shared.observability.document_index_logger import DocumentIndexLogger
from app.shared.observability.document_process_logger import DocumentProcessLogger
from app.shared.observability.document_upload_logger import DocumentUploadLogger


class _Writer:
    """测试用日志写入器替身。"""
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: dict) -> bool:
        self.events.append(dict(event))
        return True


class DocumentLogCorrelationTest(unittest.TestCase):
    """验证四个文档处理阶段的链路标识注入与因果追溯关系。"""
    def test_four_stages_share_workflow_and_have_distinct_operations(self) -> None:
        workflow_id = "workflow-document-7"
        loggers = (
            DocumentUploadLogger(
                operation_context=DocumentOperationContext.create(
                    workflow_id=workflow_id,
                    operation_id="operation-upload",
                )
            ),
            DocumentProcessLogger(
                document_id=7,
                operation_context=DocumentOperationContext.create(
                    workflow_id=workflow_id,
                    operation_id="operation-process",
                    parent_operation_id="operation-upload",
                ),
            ),
            DocumentChunkLogger(
                document_id=7,
                operation_context=DocumentOperationContext.create(
                    workflow_id=workflow_id,
                    operation_id="operation-chunk",
                ),
            ),
            DocumentIndexLogger(
                document_id=7,
                operation_context=DocumentOperationContext.create(
                    workflow_id=workflow_id,
                    operation_id="operation-index",
                ),
            ),
        )
        events = []
        for logger in loggers:
            writer = _Writer()
            logger.writer = writer
            logger.write(
                event=f"document_{logger.stage}_test",
                phase="execute",
                level="info",
                message="test",
            )
            events.append(writer.events[0])

        self.assertEqual(
            {event["workflow_id"] for event in events},
            {workflow_id},
        )
        self.assertEqual(
            len({event["operation_id"] for event in events}),
            4,
        )
        self.assertEqual(
            {event["stage"] for event in events},
            {"upload", "process", "chunk", "index"},
        )
        self.assertEqual(events[1]["parent_operation_id"], "operation-upload")
        self.assertTrue(all(event["attempt"] == 1 for event in events))


if __name__ == "__main__":
    unittest.main()
