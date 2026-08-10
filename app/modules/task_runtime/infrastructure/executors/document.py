"""未启用 Agent Provider 时直接调用 Use Case 的确定性后备 Executor。"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel

from app.modules.document.application.errors import DocumentApplicationError
from app.modules.task_runtime.application.dto import (
    TaskExecutorResult,
    TaskRuntimeContext,
)
from app.modules.task_runtime.application.errors import TaskExecutionError
from app.modules.task_runtime.application.schemas import (
    BuildDocumentChunksTaskOutput,
    BuildDocumentChunksTaskPayload,
    IndexDocumentVectorsTaskOutput,
    IndexDocumentVectorsTaskPayload,
    ProcessDocumentTaskOutput,
    ProcessDocumentTaskPayload,
)
from app.shared.observability.correlation import DocumentOperationContext


def _operation_context(context: TaskRuntimeContext) -> DocumentOperationContext:
    return DocumentOperationContext(
        workflow_id=context.workflow_id,
        operation_id=context.operation_id,
        attempt=context.attempt,
    )


async def _execute_document_use_case(call):
    try:
        return await asyncio.to_thread(call)
    except DocumentApplicationError as exc:
        raise TaskExecutionError(
            "document_operation_rejected",
            str(exc),
            retryable=exc.status_code >= 500,
            blocked=exc.status_code in {400, 404, 409},
        ) from exc


class DeterministicProcessDocumentExecutor:
    def __init__(self, use_case) -> None:
        self._use_case = use_case

    async def execute(
        self,
        payload: BaseModel,
        context: TaskRuntimeContext,
    ) -> TaskExecutorResult:
        validated = ProcessDocumentTaskPayload.model_validate(payload)
        result = await _execute_document_use_case(
            lambda: self._use_case.execute(
                validated.document_id,
                operation_context=_operation_context(context),
            )
        )
        output = ProcessDocumentTaskOutput(
            document_id=result.document_id,
            status=result.status,
            cleaned_uri=result.cleaned_uri,
        )
        return TaskExecutorResult(
            output_json=output.model_dump(mode="json"),
            resource_refs=[f"document:{result.document_id}"],
        )


class DeterministicBuildDocumentChunksExecutor:
    def __init__(self, use_case) -> None:
        self._use_case = use_case

    async def execute(
        self,
        payload: BaseModel,
        context: TaskRuntimeContext,
    ) -> TaskExecutorResult:
        validated = BuildDocumentChunksTaskPayload.model_validate(payload)
        result = await _execute_document_use_case(
            lambda: self._use_case.execute(
                validated.document_id,
                operation_context=_operation_context(context),
            )
        )
        output = BuildDocumentChunksTaskOutput(
            document_id=result.document_id,
            status=result.status,
            parent_count=result.parent_count,
            child_count=result.child_count,
        )
        return TaskExecutorResult(
            output_json=output.model_dump(mode="json"),
            resource_refs=[f"document:{result.document_id}"],
        )


class DeterministicIndexDocumentVectorsExecutor:
    def __init__(self, use_case) -> None:
        self._use_case = use_case

    async def execute(
        self,
        payload: BaseModel,
        context: TaskRuntimeContext,
    ) -> TaskExecutorResult:
        validated = IndexDocumentVectorsTaskPayload.model_validate(payload)
        result = await _execute_document_use_case(
            lambda: self._use_case.execute(
                validated.document_id,
                operation_context=_operation_context(context),
            )
        )
        output = IndexDocumentVectorsTaskOutput(
            document_id=result.document_id,
            status=result.status,
            indexed_chunks=result.indexed_chunks,
            failed_chunks=result.failed_chunks,
        )
        return TaskExecutorResult(
            output_json=output.model_dump(mode="json"),
            resource_refs=[f"document:{result.document_id}"],
        )
