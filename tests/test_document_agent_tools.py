"""Document Agent Function Tool 的适配、权限、审计与 Catalog 测试。"""

from __future__ import annotations

import json
import unittest
from datetime import datetime
from unittest import mock

from agents import RunContextWrapper
from agents.tool_context import ToolContext

from app.agent_runtime.audit import AgentToolAuditLogger
from app.agent_runtime.context import (
    AgentToolContext,
    ContextToolServices,
    DocumentToolServices,
)
from app.agent_runtime.errors import ToolNotAvailableError
from app.modules.document.agent_tools.catalog import (
    DOCUMENT_COLLECTOR_TOOLS,
    get_document_executor_tool_descriptors,
    get_document_executor_tools,
    resolve_document_tool,
    resolve_document_executor_tool,
)
from app.modules.document.agent_tools.command_tools import (
    process_document,
    build_document_chunks_handler,
    index_document_vectors_handler,
    process_document_handler,
)
from app.modules.document.agent_tools.query_tools import (
    get_document,
    get_document_handler,
    search_documents_handler,
)
from app.modules.document.agent_tools.schemas import (
    BuildDocumentChunksToolInput,
    GetDocumentToolInput,
    IndexDocumentVectorsToolInput,
    ProcessDocumentToolInput,
    SearchDocumentsToolInput,
)
from app.modules.document.application.dto import (
    BuildChunksResult,
    DocumentResult,
    DocumentListItem,
    IndexVectorsResult,
    ProcessDocumentResult,
    SearchDocumentsResult,
)
from app.modules.document.application.errors import DocumentApplicationError


NOW = datetime(2026, 8, 2, 12, 0, 0)


class _AuditWriter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: dict) -> bool:
        self.events.append(dict(event))
        return True


def _service(result=None, error=None):
    service = mock.Mock()
    if error is not None:
        service.execute.side_effect = error
    else:
        service.execute.return_value = result
    return service


def _document_result() -> DocumentResult:
    return DocumentResult(
        id=7,
        doc_code="DOC_7",
        kb_id=3,
        domain_code="policy",
        business_scene=None,
        title="测试文档",
        original_filename="test.txt",
        file_size=128,
        source_type="txt",
        source_uri="storage/raw/local/DOC_7.txt",
        cleaned_uri="storage/cleaned/DOC_7.cleaned.txt",
        content_hash="a" * 64,
        active_content_hash="a" * 64,
        lifecycle_status="active",
        storage_status="active",
        version=1,
        status="processed",
        replaced_by=None,
        risk_level="low",
        effective_at=None,
        expired_at=None,
        created_by_actor_code="actor",
        created_at=NOW,
        updated_at=NOW,
        indexed_at=None,
    )


def _context(
    *,
    permissions: frozenset[str],
    writer: _AuditWriter,
    process_result=None,
    process_error=None,
) -> tuple[AgentToolContext, DocumentToolServices]:
    services = DocumentToolServices(
        get_document=_service(_document_result()),
        list_documents=_service(),
        search_documents=_service(),
        get_document_pipeline_state=_service(),
        list_document_artifacts=_service(),
        search_document_artifacts=_service(),
        list_parent_blocks=_service(),
        list_child_chunks=_service(),
        get_document_chunk_statistics=_service(),
        get_knowledge_base_statistics=_service(),
        process_document=_service(process_result, process_error),
        build_chunks=_service(
            BuildChunksResult(
                document_id=7,
                doc_code="DOC_7",
                source_type="txt",
                parent_count=2,
                child_count=4,
                status="chunked",
            )
        ),
        index_vectors=_service(
            IndexVectorsResult(
                document_id=7,
                total_chunks=4,
                indexed_chunks=4,
                failed_chunks=0,
                status="indexed",
            )
        ),
    )
    context = AgentToolContext(
        trace_id="trace-1",
        agent_run_id="run-1",
        agent_name="document-executor",
        conversation_id="conversation-1",
        turn_id="turn-1",
        task_id="task-1",
        actor_code="actor-1",
        permissions=permissions,
        document_services=services,
        context_services=ContextToolServices(),
        workflow_id="workflow-1",
        execution_id="execution-1",
        operation_id="operation-1",
        attempt=2,
        audit_logger=AgentToolAuditLogger(writer),
    )
    return context, services


class DocumentAgentToolsTest(unittest.TestCase):
    def test_query_tool_calls_use_case_and_maps_result(self) -> None:
        writer = _AuditWriter()
        context, services = _context(
            permissions=frozenset({"document:read"}),
            writer=writer,
        )

        output = get_document_handler(
            RunContextWrapper(context),
            GetDocumentToolInput(document_id=7),
        )

        self.assertEqual(output.outcome, "succeeded")
        self.assertEqual(output.document.id, 7)
        services.get_document.execute.assert_called_once_with(7)

    def test_search_documents_maps_advanced_query_and_pagination(self) -> None:
        writer = _AuditWriter()
        context, services = _context(
            permissions=frozenset({"document:read"}),
            writer=writer,
        )
        services.search_documents.execute.return_value = SearchDocumentsResult(
            items=[
                DocumentListItem.model_validate(_document_result())
            ],
            total=1,
            limit=20,
            offset=5,
        )

        output = search_documents_handler(
            RunContextWrapper(context),
            SearchDocumentsToolInput(
                kb_ids=[3],
                statuses=["processed"],
                keyword="测试",
                sort_by="updated_at",
                limit=20,
                offset=5,
            ),
        )

        self.assertEqual(output.outcome, "succeeded")
        self.assertEqual(output.documents[0].id, 7)
        query = services.search_documents.execute.call_args.args[0]
        self.assertEqual(query.kb_ids, [3])
        self.assertEqual(query.statuses, ["processed"])
        self.assertEqual(query.sort_by, "updated_at")
        self.assertEqual(output.resource_refs, ["knowledge_base:3"])

    def test_command_tools_map_all_existing_use_case_results(self) -> None:
        writer = _AuditWriter()
        process_result = ProcessDocumentResult(
            document_id=7,
            doc_code="DOC_7",
            source_type="txt",
            source_uri="storage/raw/local/DOC_7.txt",
            cleaned_uri="storage/cleaned/DOC_7.cleaned.txt",
            status="processed",
        )
        context, services = _context(
            permissions=frozenset(
                {
                    "document:process",
                    "document:chunks:build",
                    "document:vectors:index",
                }
            ),
            writer=writer,
            process_result=process_result,
        )

        wrapper = RunContextWrapper(context)
        process_output = process_document_handler(
            wrapper,
            ProcessDocumentToolInput(document_id=7),
        )
        chunks_output = build_document_chunks_handler(
            wrapper,
            BuildDocumentChunksToolInput(document_id=7),
        )
        vectors_output = index_document_vectors_handler(
            wrapper,
            IndexDocumentVectorsToolInput(document_id=7),
        )

        self.assertEqual(process_output.document_status, "processed")
        self.assertEqual(chunks_output.child_count, 4)
        self.assertEqual(vectors_output.indexed_chunks, 4)
        operation_contexts = []
        for service in (
            services.process_document,
            services.build_chunks,
            services.index_vectors,
        ):
            call = service.execute.call_args
            self.assertEqual(call.args, (7,))
            operation_context = call.kwargs["operation_context"]
            self.assertEqual(operation_context.workflow_id, "workflow-1")
            self.assertEqual(operation_context.attempt, 2)
            operation_contexts.append(operation_context)
        self.assertEqual(
            {item.operation_id for item in operation_contexts},
            {"operation-1"},
        )

    def test_business_rejection_is_structured(self) -> None:
        writer = _AuditWriter()
        context, _services = _context(
            permissions=frozenset({"document:process"}),
            writer=writer,
            process_error=DocumentApplicationError(
                409,
                "当前文档状态不允许处理: processed",
            ),
        )

        output = process_document_handler(
            RunContextWrapper(context),
            ProcessDocumentToolInput(document_id=7),
        )

        self.assertEqual(output.outcome, "rejected")
        self.assertEqual(output.result_code, "document_state_conflict")
        self.assertFalse(output.retryable)
        self.assertNotIn("Traceback", output.message)

    def test_timeout_failure_is_retryable_and_safe(self) -> None:
        writer = _AuditWriter()
        context, _services = _context(
            permissions=frozenset({"document:process"}),
            writer=writer,
            process_error=TimeoutError("secret upstream details"),
        )

        output = process_document_handler(
            RunContextWrapper(context),
            ProcessDocumentToolInput(document_id=7),
        )

        self.assertEqual(output.outcome, "failed")
        self.assertEqual(output.result_code, "tool_execution_failed")
        self.assertTrue(output.retryable)
        self.assertNotIn("secret upstream details", output.message)

    def test_permission_denial_does_not_call_use_case(self) -> None:
        writer = _AuditWriter()
        context, services = _context(
            permissions=frozenset(),
            writer=writer,
        )

        output = build_document_chunks_handler(
            RunContextWrapper(context),
            BuildDocumentChunksToolInput(document_id=7),
        )

        self.assertEqual(output.outcome, "rejected")
        self.assertEqual(output.result_code, "permission_denied")
        services.build_chunks.execute.assert_not_called()

    def test_audit_events_keep_invocation_correlation(self) -> None:
        writer = _AuditWriter()
        context, _services = _context(
            permissions=frozenset({"document:read"}),
            writer=writer,
        )

        get_document_handler(
            RunContextWrapper(context),
            GetDocumentToolInput(document_id=7),
        )

        self.assertEqual(len(writer.events), 2)
        started, completed = writer.events
        self.assertEqual(
            started["event"],
            "agent_tool_invocation_started",
        )
        self.assertEqual(
            completed["event"],
            "agent_tool_invocation_succeeded",
        )
        self.assertEqual(
            started["invocation_id"],
            completed["invocation_id"],
        )
        self.assertEqual(completed["trace_id"], "trace-1")
        self.assertEqual(completed["task_id"], "task-1")
        self.assertEqual(completed["workflow_id"], "workflow-1")
        self.assertEqual(completed["execution_id"], "execution-1")
        self.assertEqual(completed["operation_id"], "operation-1")
        self.assertEqual(completed["attempt"], 2)
        self.assertEqual(completed["resource_refs"], ["document:7"])

    def test_catalogs_expose_only_capability_appropriate_tools(self) -> None:
        collector_names = {tool.name for tool in DOCUMENT_COLLECTOR_TOOLS}
        process_names = {
            tool.name
            for tool in get_document_executor_tools("document.process")
        }
        chunks_names = {
            tool.name
            for tool in get_document_executor_tools("document.build_chunks")
        }
        vectors_names = {
            tool.name
            for tool in get_document_executor_tools("document.index_vectors")
        }

        self.assertEqual(
            collector_names,
            {
                "get_document",
                "search_documents",
                "get_document_pipeline_state",
                "list_document_artifacts",
                "search_document_artifacts",
                "list_parent_blocks",
                "list_child_chunks",
                "get_document_chunk_statistics",
                "get_knowledge_base_statistics",
            },
        )
        self.assertNotIn("process_document", collector_names)
        self.assertEqual(
            process_names,
            {
                "get_document",
                "get_document_pipeline_state",
                "process_document",
            },
        )
        self.assertEqual(
            chunks_names,
            {
                "get_document",
                "get_document_pipeline_state",
                "get_document_chunk_statistics",
                "build_document_chunks",
            },
        )
        self.assertEqual(
            vectors_names,
            {
                "get_document",
                "get_document_pipeline_state",
                "get_document_chunk_statistics",
                "index_document_vectors",
            },
        )
        descriptors = get_document_executor_tool_descriptors(
            "document.process"
        )
        process_descriptor = next(
            item for item in descriptors if item.name == "process_document"
        )
        self.assertTrue(process_descriptor.side_effect)
        self.assertFalse(process_descriptor.approval_required)
        self.assertFalse(process_document.needs_approval)

        with self.assertRaises(ToolNotAvailableError):
            resolve_document_executor_tool(
                "document.process",
                "index_document_vectors",
            )

    def test_unregistered_tool_cannot_be_resolved(self) -> None:
        with self.assertRaises(ToolNotAvailableError):
            resolve_document_tool(
                "document_collector",
                "index_document_vectors",
            )


class DocumentFunctionToolIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_sdk_function_tool_invokes_same_handler(self) -> None:
        writer = _AuditWriter()
        context, services = _context(
            permissions=frozenset({"document:read"}),
            writer=writer,
        )
        arguments = json.dumps({"tool_input": {"document_id": 7}})
        tool_context = ToolContext(
            context=context,
            tool_name=get_document.name,
            tool_call_id="call-1",
            tool_arguments=arguments,
        )

        output = await get_document.on_invoke_tool(
            tool_context,
            arguments,
        )

        self.assertEqual(output.outcome, "succeeded")
        services.get_document.execute.assert_called_once_with(7)


if __name__ == "__main__":
    unittest.main()
