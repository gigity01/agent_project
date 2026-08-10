"""把 capability-scoped Agent Run 适配为 Task Executor Port。"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from agents import Agent, RunConfig, Runner
from pydantic import BaseModel, ValidationError

from app.agent_runtime.audit import AgentToolAuditLogger
from app.agent_runtime.context import (
    AgentToolContext,
    ContextToolServices,
    DocumentToolServices,
)
from app.modules.document.agent_tools.schemas import (
    BuildDocumentChunksToolOutput,
    IndexDocumentVectorsToolOutput,
    ProcessDocumentToolOutput,
    ToolResult,
)
from app.modules.task_runtime.application.dto import (
    TaskExecutorResult,
    TaskRuntimeContext,
)
from app.modules.task_runtime.application.errors import TaskExecutionError
from app.modules.task_runtime.application.schemas import (
    BuildDocumentChunksTaskOutput,
    IndexDocumentVectorsTaskOutput,
    ProcessDocumentTaskOutput,
)


DOCUMENT_EXECUTOR_ACTOR_CODE = "document_executor_agent"
DEFAULT_DOCUMENT_EXECUTOR_MAX_TURNS = 8


def adapt_process_document_output(
    output: ToolResult,
) -> TaskExecutorResult:
    result = ProcessDocumentToolOutput.model_validate(output)
    task_output = ProcessDocumentTaskOutput(
        document_id=result.document_id,
        status=result.document_status,
        cleaned_uri=result.cleaned_uri,
    )
    return TaskExecutorResult(
        output_json=task_output.model_dump(mode="json"),
        resource_refs=result.resource_refs,
    )


def adapt_build_document_chunks_output(
    output: ToolResult,
) -> TaskExecutorResult:
    result = BuildDocumentChunksToolOutput.model_validate(output)
    task_output = BuildDocumentChunksTaskOutput(
        document_id=result.document_id,
        status=result.document_status,
        parent_count=result.parent_count,
        child_count=result.child_count,
    )
    return TaskExecutorResult(
        output_json=task_output.model_dump(mode="json"),
        resource_refs=result.resource_refs,
    )


def adapt_index_document_vectors_output(
    output: ToolResult,
) -> TaskExecutorResult:
    result = IndexDocumentVectorsToolOutput.model_validate(output)
    task_output = IndexDocumentVectorsTaskOutput(
        document_id=result.document_id,
        status=result.document_status,
        indexed_chunks=result.indexed_chunks,
        failed_chunks=result.failed_chunks,
    )
    return TaskExecutorResult(
        output_json=task_output.model_dump(mode="json"),
        resource_refs=result.resource_refs,
    )


class AgentTaskExecutor:
    """执行受限 Agent，并仅信任唯一 Command Tool 的结构化输出。"""

    def __init__(
        self,
        *,
        agent: Agent[AgentToolContext],
        executor_code: str,
        primary_tool_name: str,
        tool_output_model: type[ToolResult],
        output_adapter: Callable[[ToolResult], TaskExecutorResult],
        document_services: DocumentToolServices,
        permissions: frozenset[str],
        run_config: RunConfig,
        max_turns: int = DEFAULT_DOCUMENT_EXECUTOR_MAX_TURNS,
        runner: Callable[..., Any] = Runner.run,
        audit_logger_factory: Callable[[], AgentToolAuditLogger] = (
            AgentToolAuditLogger
        ),
    ) -> None:
        if primary_tool_name not in {tool.name for tool in agent.tools}:
            raise ValueError("Executor Agent 未暴露指定 Command Tool")
        self._agent = agent
        self._executor_code = executor_code
        self._primary_tool_name = primary_tool_name
        self._tool_output_model = tool_output_model
        self._output_adapter = output_adapter
        self._document_services = document_services
        self._permissions = permissions
        self._run_config = run_config
        self._max_turns = max_turns
        self._runner = runner
        self._audit_logger_factory = audit_logger_factory

    async def execute(
        self,
        payload: BaseModel,
        context: TaskRuntimeContext,
    ) -> TaskExecutorResult:
        document_id = getattr(payload, "document_id", None)
        if not isinstance(document_id, int):
            raise TaskExecutionError(
                "executor_invalid_task_payload",
                "Document Executor Task Payload 缺少 document_id",
                retryable=False,
                blocked=True,
            )
        agent_context = AgentToolContext(
            trace_id=f"trace_{uuid4().hex}",
            agent_run_id=context.agent_run_id,
            agent_name=self._agent.name,
            conversation_id=context.conversation_id,
            turn_id=context.turn_id,
            task_id=context.task_id,
            actor_code=DOCUMENT_EXECUTOR_ACTOR_CODE,
            permissions=self._permissions,
            document_services=self._document_services,
            context_services=ContextToolServices(),
            plan_id=context.plan_id,
            workflow_id=context.workflow_id,
            execution_id=context.execution_id,
            operation_id=context.operation_id,
            task_document_id=document_id,
            attempt=context.attempt,
            audit_logger=self._audit_logger_factory(),
        )
        agent_input = json.dumps(
            {
                "executor_code": self._executor_code,
                "primary_tool_name": self._primary_tool_name,
                "task_payload": payload.model_dump(mode="json"),
            },
            ensure_ascii=False,
        )
        try:
            run_result = await self._runner(
                self._agent,
                agent_input,
                context=agent_context,
                max_turns=self._max_turns,
                run_config=self._run_config,
            )
        except TaskExecutionError:
            raise
        except Exception as exc:
            raise TaskExecutionError(
                "executor_agent_run_failed",
                "Executor Agent 运行失败",
                retryable=True,
            ) from exc

        try:
            output = self._validate_tool_output(run_result.final_output)
        except (TypeError, ValidationError, ValueError) as exc:
            raise TaskExecutionError(
                "executor_command_not_completed",
                "Executor Agent 未返回有效的 Command Tool Output",
                retryable=True,
            ) from exc

        if output.document_id != document_id:
            raise TaskExecutionError(
                "task_scope_violation",
                "Command Tool Output 与 Task 资源范围不一致",
                retryable=False,
                blocked=True,
            )
        if output.outcome == "rejected":
            raise TaskExecutionError(
                output.result_code,
                output.message,
                retryable=False,
                blocked=True,
            )
        if output.outcome == "failed":
            raise TaskExecutionError(
                output.result_code,
                output.message,
                retryable=output.retryable,
            )

        try:
            return self._output_adapter(output)
        except (TypeError, ValidationError, ValueError) as exc:
            raise TaskExecutionError(
                "executor_invalid_command_output",
                "Command Tool 成功输出不符合 Task Result 契约",
                retryable=False,
            ) from exc

    def _validate_tool_output(self, output: Any) -> ToolResult:
        if isinstance(output, str):
            return self._tool_output_model.model_validate_json(output)
        return self._tool_output_model.model_validate(output)
