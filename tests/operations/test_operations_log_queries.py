"""基于 JSONL 日志文件的运维查询与时间线聚合用例测试。

核心业务不变量：
1. JSONL 日志多源聚合与时间线构建：
   - 验证对各个阶段（upload, process, chunk, index）JSONL 日志文件的多维聚合与时间线生成（Workflow Timeline, Operation Timeline, Task Tool Timeline）。
2. 过滤与结构化转换：
   - 支持按时间范围、workflow_id、operation_id、document_id、event_type 与 outcome 过滤并按时间升序排序。
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.modules.operations.application.dto import (
    AgentToolAuditQuery,
    DocumentBusinessLogQuery,
    DocumentOperationTimelineQuery,
    DocumentTimelineQuery,
    DocumentWorkflowTimelineQuery,
    ToolTimelineQuery,
)
from app.modules.operations.application.errors import OperationsQueryError
from app.modules.operations.application.query_service import OperationsQueryService
from app.modules.operations.application.use_cases import (
    GetDocumentOperationTimelineUseCase,
    GetDocumentWorkflowTimelineUseCase,
    QueryDocumentLogEventsUseCase,
)
from app.modules.operations.infrastructure.jsonl_repository import (
    JsonlLogRepository,
    JsonlLogSource,
)
from app.shared.observability.jsonl_writer import JsonlEventWriter


def _time(minute: int) -> str:
    """生成测试用 UTC ISO 时间戳字符串。"""
    return datetime(
        2026,
        8,
        3,
        12,
        minute,
        tzinfo=timezone.utc,
    ).isoformat()


class OperationsLogQueriesTest(unittest.TestCase):
    """验证 OperationsQueryService 与用例对 JSONL 文件日志的高级查询与聚合。"""
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.stage_dirs = {
            stage: root / "document_lifecycle" / stage
            for stage in ("upload", "process", "chunk", "index")
        }
        self.audit_dir = root / "agent_tools"
        self._write_document_events()
        self._write_audit_events()
        document_repository = JsonlLogRepository(
            tuple(
                JsonlLogSource(stage, directory, stage)
                for stage, directory in self.stage_dirs.items()
            )
        )
        audit_repository = JsonlLogRepository(
            (JsonlLogSource("agent_tool", self.audit_dir, "agent-tool"),)
        )
        self.service = OperationsQueryService(
            document_logs=document_repository,
            agent_tool_logs=audit_repository,
        )
        self.document_repository = document_repository
        self.audit_repository = audit_repository

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_document_events(self) -> None:
        events = (
            (
                "upload",
                {
                    "event_id": "doc-event-1",
                    "workflow_id": "workflow-7",
                    "operation_id": "upload-operation",
                    "parent_operation_id": None,
                    "attempt": 1,
                    "event": "document_upload_completed",
                    "stage": "upload",
                    "phase": "finalize",
                    "level": "info",
                    "message": "上传完成",
                    "document_id": 7,
                    "doc_code": "DOC_7",
                    "kb_id": 3,
                    "status_after": "uploaded",
                    "duration_ms": 10,
                    "created_at": _time(1),
                },
            ),
            (
                "process",
                {
                    "event_id": "doc-event-2",
                    "workflow_id": "workflow-7",
                    "operation_id": "process-operation-1",
                    "parent_operation_id": None,
                    "attempt": 1,
                    "event": "document_process_failed",
                    "stage": "process",
                    "phase": "execute",
                    "level": "error",
                    "message": "处理失败",
                    "document_id": 7,
                    "doc_code": "DOC_7",
                    "kb_id": 3,
                    "error_type": "RuntimeError",
                    "error_message": "转换器不可用",
                    "status_before": "processing",
                    "status_after": "failed",
                    "state_updated": True,
                    "duration_ms": 20,
                    "created_at": _time(2),
                },
            ),
            (
                "chunk",
                {
                    "event_id": "doc-event-3",
                    "workflow_id": "workflow-8",
                    "operation_id": "chunk-operation",
                    "parent_operation_id": None,
                    "attempt": 1,
                    "event": "document_chunk_completed",
                    "stage": "chunk",
                    "phase": "finalize",
                    "level": "info",
                    "message": "切块完成",
                    "document_id": 8,
                    "doc_code": "DOC_8",
                    "kb_id": 3,
                    "duration_ms": 30,
                    "created_at": _time(3),
                },
            ),
            (
                "process",
                {
                    "event_id": "doc-event-4",
                    "workflow_id": "workflow-7",
                    "operation_id": "process-operation-2",
                    "parent_operation_id": None,
                    "attempt": 2,
                    "event": "document_process_completed",
                    "stage": "process",
                    "phase": "finalize",
                    "level": "info",
                    "message": "处理重试完成",
                    "document_id": 7,
                    "doc_code": "DOC_7",
                    "kb_id": 3,
                    "status_before": "processing",
                    "status_after": "processed",
                    "duration_ms": 40,
                    "created_at": _time(4),
                },
            ),
        )
        for stage, event in events:
            JsonlEventWriter(self.stage_dirs[stage], stage).write(event)

    def _write_audit_events(self) -> None:
        writer = JsonlEventWriter(self.audit_dir, "agent-tool")
        events = (
            {
                "event_id": "audit-1",
                "invocation_id": "invocation-1",
                "event": "agent_tool_invocation_started",
                "trace_id": "trace-1",
                "agent_run_id": "run-1",
                "conversation_id": "conversation-1",
                "turn_id": "turn-1",
                "task_id": "task-1",
                "agent_name": "document-executor",
                "tool_name": "process_document",
                "actor_code": "actor-1",
                "resource_refs": ["document:7"],
                "duration_ms": 0,
                "created_at": _time(4),
            },
            {
                "event_id": "audit-2",
                "invocation_id": "invocation-1",
                "event": "agent_tool_invocation_failed",
                "trace_id": "trace-1",
                "agent_run_id": "run-1",
                "conversation_id": "conversation-1",
                "turn_id": "turn-1",
                "task_id": "task-1",
                "agent_name": "document-executor",
                "tool_name": "process_document",
                "actor_code": "actor-1",
                "resource_refs": ["document:7"],
                "duration_ms": 20,
                "result_code": "tool_execution_failed",
                "retryable": True,
                "created_at": _time(5),
            },
            {
                "event_id": "audit-3",
                "invocation_id": "invocation-2",
                "event": "agent_tool_invocation_started",
                "trace_id": "trace-1",
                "agent_run_id": "run-1",
                "conversation_id": "conversation-1",
                "turn_id": "turn-1",
                "task_id": "task-1",
                "agent_name": "document-executor",
                "tool_name": "process_document",
                "actor_code": "actor-1",
                "resource_refs": ["document:7"],
                "duration_ms": 0,
                "created_at": _time(6),
            },
            {
                "event_id": "audit-4",
                "invocation_id": "invocation-2",
                "event": "agent_tool_invocation_succeeded",
                "trace_id": "trace-1",
                "agent_run_id": "run-1",
                "conversation_id": "conversation-1",
                "turn_id": "turn-1",
                "task_id": "task-1",
                "agent_name": "document-executor",
                "tool_name": "process_document",
                "actor_code": "actor-1",
                "resource_refs": ["document:7"],
                "duration_ms": 30,
                "result_code": "document_processed",
                "retryable": False,
                "created_at": _time(7),
            },
        )
        for event in events:
            writer.write(event)

    def test_business_log_query_filters_failures_and_pages_with_cursor(self) -> None:
        failed = self.service.query_document_business_logs(
            DocumentBusinessLogQuery(
                document_ids=[7],
                failed_only=True,
            )
        )
        first_page = self.service.query_document_business_logs(
            DocumentBusinessLogQuery(kb_ids=[3], limit=1)
        )
        second_page = self.service.query_document_business_logs(
            DocumentBusinessLogQuery(
                kb_ids=[3],
                limit=1,
                cursor=first_page.next_cursor,
            )
        )

        self.assertEqual([item.event for item in failed.items], ["document_process_failed"])
        self.assertEqual(failed.items[0].error_summary, "转换器不可用")
        self.assertIsNotNone(first_page.next_cursor)
        self.assertNotEqual(
            first_page.items[0].event_id,
            second_page.items[0].event_id,
        )

    def test_document_timelines_are_chronological_and_diagnostic(self) -> None:
        execution = self.service.get_document_execution_timeline(
            DocumentTimelineQuery(document_id=7)
        )
        failures = self.service.get_document_failure_timeline(
            DocumentTimelineQuery(document_id=7)
        )

        self.assertEqual(
            [item.stage for item in execution.events],
            ["upload", "process", "process"],
        )
        self.assertEqual(failures.failures[0].error_type, "RuntimeError")
        self.assertTrue(failures.failures[0].state_updated)

    def test_named_use_cases_query_operation_and_workflow_timelines(self) -> None:
        query_events = QueryDocumentLogEventsUseCase(self.service)
        get_operation = GetDocumentOperationTimelineUseCase(self.service)
        get_workflow = GetDocumentWorkflowTimelineUseCase(self.service)

        filtered = query_events.execute(
            DocumentBusinessLogQuery(
                workflow_ids=["workflow-7"],
                attempts=[2],
            )
        )
        operation = get_operation.execute(
            DocumentOperationTimelineQuery(
                operation_id="process-operation-1"
            )
        )
        workflow = get_workflow.execute(
            DocumentWorkflowTimelineQuery(workflow_id="workflow-7")
        )

        self.assertEqual(
            [item.event_id for item in filtered.items],
            ["doc-event-4"],
        )
        self.assertEqual(operation.workflow_id, "workflow-7")
        self.assertEqual(operation.attempt, 1)
        self.assertEqual(
            [item.operation_id for item in workflow.events],
            [
                "upload-operation",
                "process-operation-1",
                "process-operation-2",
            ],
        )

    def test_audit_query_and_timelines_show_retry_then_success(self) -> None:
        audits = self.service.query_agent_tool_audits(
            AgentToolAuditQuery(
                task_id="task-1",
                tool_names=["process_document"],
                retryable=True,
            )
        )
        task_timeline = self.service.get_task_tool_timeline(
            ToolTimelineQuery(identifier="task-1")
        )
        run_timeline = self.service.get_agent_run_tool_timeline(
            ToolTimelineQuery(identifier="run-1")
        )

        self.assertEqual([item.event_id for item in audits.items], ["audit-2"])
        self.assertEqual(
            [item.outcome for item in task_timeline.invocations],
            ["failed", "succeeded"],
        )
        self.assertTrue(task_timeline.invocations[0].retryable)
        self.assertEqual(len(run_timeline.invocations), 2)

    def test_invalid_cursor_is_rejected_without_accepting_file_paths(self) -> None:
        with self.assertRaises(OperationsQueryError):
            self.audit_repository.scan(
                predicate=lambda _event: True,
                created_from=None,
                created_to=None,
                limit=10,
                cursor="not-a-valid-cursor",
            )

    def test_cursor_cannot_be_reused_for_a_different_log_source(self) -> None:
        document_page = self.document_repository.scan(
            predicate=lambda _event: True,
            created_from=None,
            created_to=None,
            limit=1,
        )

        with self.assertRaises(OperationsQueryError):
            self.audit_repository.scan(
                predicate=lambda _event: True,
                created_from=None,
                created_to=None,
                limit=10,
                cursor=document_page.next_cursor,
            )


if __name__ == "__main__":
    unittest.main()
