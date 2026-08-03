"""Operations 只读 Agent Tool 测试。"""

from __future__ import annotations

import unittest
from datetime import datetime
from unittest import mock

from agents import RunContextWrapper

from app.agent_runtime.audit import AgentToolAuditLogger
from app.agent_runtime.context import (
    AgentToolContext,
    ContextToolServices,
    OperationsToolServices,
)
from app.modules.operations.agent_tools.catalog import OPERATIONS_COLLECTOR_TOOLS
from app.modules.operations.agent_tools.query_tools import (
    get_task_tool_timeline_handler,
    query_document_business_logs_handler,
)
from app.modules.operations.agent_tools.schemas import (
    GetTaskToolTimelineToolInput,
    QueryDocumentBusinessLogsToolInput,
)
from app.modules.operations.application.dto import (
    DocumentBusinessLogEvent,
    DocumentBusinessLogPage,
    ToolInvocationTimelineItem,
    ToolTimelineResult,
)


NOW = datetime(2026, 8, 3, 12, 0, 0)


class _Writer:
    def write(self, _event: dict) -> bool:
        return True


def _context(*, permissions: frozenset[str]):
    service = mock.Mock()
    service.query_document_business_logs.return_value = DocumentBusinessLogPage(
        items=[
            DocumentBusinessLogEvent(
                event_id="event-1",
                run_id="run-1",
                document_id=7,
                doc_code="DOC_7",
                kb_id=3,
                stage="process",
                event="document_process_failed",
                phase="execute",
                level="error",
                message="处理失败",
                error_type="RuntimeError",
                error_summary="转换失败",
                status_before="processing",
                status_after="failed",
                state_updated=True,
                created_at=NOW,
            )
        ],
        next_cursor=None,
    )
    service.get_task_tool_timeline.return_value = ToolTimelineResult(
        identifier="task-1",
        invocations=[
            ToolInvocationTimelineItem(
                invocation_id="invocation-1",
                trace_id="trace-1",
                agent_run_id="run-1",
                conversation_id="conversation-1",
                turn_id="turn-1",
                task_id="task-1",
                agent_name="executor",
                tool_name="process_document",
                actor_code="actor-1",
                resource_refs=["document:7"],
                started_at=NOW,
                completed_at=NOW,
                outcome="succeeded",
                result_code="document_processed",
                retryable=False,
                duration_ms=10,
            )
        ],
        truncated=False,
    )
    context = AgentToolContext(
        trace_id="trace-query",
        agent_run_id="run-query",
        agent_name="operations-collector",
        conversation_id="conversation-1",
        turn_id="turn-query",
        task_id="task-query",
        actor_code="actor-query",
        permissions=permissions,
        document_services=mock.Mock(),
        context_services=ContextToolServices(),
        operations_services=OperationsToolServices(query_service=service),
        audit_logger=AgentToolAuditLogger(_Writer()),
    )
    return context, service


class OperationsAgentToolsTest(unittest.TestCase):
    def test_catalog_exposes_business_and_audit_queries(self) -> None:
        self.assertEqual(
            {tool.name for tool in OPERATIONS_COLLECTOR_TOOLS},
            {
                "query_document_business_logs",
                "get_document_execution_timeline",
                "get_document_failure_timeline",
                "query_agent_tool_audits",
                "get_task_tool_timeline",
                "get_agent_run_tool_timeline",
            },
        )

    def test_business_log_handler_passes_filters(self) -> None:
        context, service = _context(
            permissions=frozenset({"operations:read"})
        )

        output = query_document_business_logs_handler(
            RunContextWrapper(context),
            QueryDocumentBusinessLogsToolInput(
                document_ids=[7],
                stages=["process"],
                failed_only=True,
            ),
        )

        query = service.query_document_business_logs.call_args.args[0]
        self.assertEqual(output.events[0].event_id, "event-1")
        self.assertEqual(query.document_ids, [7])
        self.assertTrue(query.failed_only)

    def test_task_timeline_handler_returns_aggregated_invocations(self) -> None:
        context, service = _context(
            permissions=frozenset({"operations:read"})
        )

        output = get_task_tool_timeline_handler(
            RunContextWrapper(context),
            GetTaskToolTimelineToolInput(task_id="task-1"),
        )

        self.assertEqual(output.invocations[0].outcome, "succeeded")
        query = service.get_task_tool_timeline.call_args.args[0]
        self.assertEqual(query.identifier, "task-1")

    def test_permission_denial_does_not_scan_logs(self) -> None:
        context, service = _context(permissions=frozenset())

        output = query_document_business_logs_handler(
            RunContextWrapper(context),
            QueryDocumentBusinessLogsToolInput(document_ids=[7]),
        )

        self.assertEqual(output.result_code, "permission_denied")
        service.query_document_business_logs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
