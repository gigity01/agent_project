"""只调用 Planning Use Case 的 Planner Function Tools。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agents import RunContextWrapper, function_tool

from app.agent_runtime.audit import execute_audited_tool_call
from app.agent_runtime.context import AgentToolContext, PlanningToolServices
from app.agent_runtime.errors import safe_tool_error_function
from app.modules.planning.agent_tools.schemas import (
    CreateBuildChunksTaskToolInput,
    CreateIndexVectorsTaskToolInput,
    CreateProcessDocumentTaskToolInput,
    FinalizePlanToolInput,
    MarkPlanUnsupportedToolInput,
    PlanningToolOutput,
)
from app.modules.planning.application.dto import (
    CreateBuildChunksTaskInput,
    CreateIndexVectorsTaskInput,
    CreateProcessDocumentTaskInput,
    FinalizePlanInput,
    MarkPlanUnsupportedInput,
)
from app.modules.planning.application.errors import PlanningApplicationError


PLANNING_WRITE_PERMISSION = "planning:write"


def _planning_scope(
    context: AgentToolContext,
) -> tuple[PlanningToolServices, str, str]:
    if context.planning_services is None:
        raise PlanningApplicationError(
            503,
            "Planning Use Cases 未配置",
            result_code="planning_not_configured",
        )
    if context.plan_id is None or context.turn_id is None:
        raise PlanningApplicationError(
            409,
            "Planner Run 缺少 Plan 或 Turn 关联上下文",
            result_code="planning_context_missing",
        )
    return context.planning_services, context.plan_id, context.turn_id


def _execute(
    ctx: RunContextWrapper[AgentToolContext],
    *,
    tool_name: str,
    success_result_code: str,
    operation: Callable[[PlanningToolServices, str, str], Any],
) -> tuple[Any | None, PlanningToolOutput | None]:
    resource_refs = [
        *([f"plan:{ctx.context.plan_id}"] if ctx.context.plan_id else []),
        *([f"turn:{ctx.context.turn_id}"] if ctx.context.turn_id else []),
    ]
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name=tool_name,
        required_permissions=(PLANNING_WRITE_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code=success_result_code,
        operation=lambda: operation(*_planning_scope(ctx.context)),
    )
    if execution.error is not None:
        return None, PlanningToolOutput(**execution.error.__dict__)
    return execution.value, None


def create_process_document_task_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: CreateProcessDocumentTaskToolInput,
) -> PlanningToolOutput:
    result, error = _execute(
        ctx,
        tool_name="create_process_document_task",
        success_result_code="process_document_task_created",
        operation=lambda services, plan_id, turn_id: (
            services.create_process_document_task.execute(
                CreateProcessDocumentTaskInput(
                    plan_id=plan_id,
                    turn_id=turn_id,
                    document_id=tool_input.document_id,
                    sequence=tool_input.sequence,
                )
            )
        ),
    )
    if error is not None:
        return error
    return PlanningToolOutput(
        outcome="succeeded",
        result_code="process_document_task_created",
        message="文档处理 Task 已创建",
        retryable=False,
        resource_refs=[f"plan:{result.plan_id}", f"task:{result.task_id}"],
        plan_id=result.plan_id,
        task_id=result.task_id,
        status=result.status,
    )


create_process_document_task = function_tool(
    name_override="create_process_document_task",
    description_override="为当前 Plan 创建一项文档处理 Task。",
    failure_error_function=safe_tool_error_function,
)(create_process_document_task_handler)


def create_build_chunks_task_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: CreateBuildChunksTaskToolInput,
) -> PlanningToolOutput:
    result, error = _execute(
        ctx,
        tool_name="create_build_chunks_task",
        success_result_code="build_chunks_task_created",
        operation=lambda services, plan_id, turn_id: (
            services.create_build_chunks_task.execute(
                CreateBuildChunksTaskInput(
                    plan_id=plan_id,
                    turn_id=turn_id,
                    document_id=tool_input.document_id,
                    sequence=tool_input.sequence,
                )
            )
        ),
    )
    if error is not None:
        return error
    return PlanningToolOutput(
        outcome="succeeded",
        result_code="build_chunks_task_created",
        message="文档切块 Task 已创建",
        retryable=False,
        resource_refs=[f"plan:{result.plan_id}", f"task:{result.task_id}"],
        plan_id=result.plan_id,
        task_id=result.task_id,
        status=result.status,
    )


create_build_chunks_task = function_tool(
    name_override="create_build_chunks_task",
    description_override="为当前 Plan 创建一项文档切块 Task。",
    failure_error_function=safe_tool_error_function,
)(create_build_chunks_task_handler)


def create_index_vectors_task_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: CreateIndexVectorsTaskToolInput,
) -> PlanningToolOutput:
    result, error = _execute(
        ctx,
        tool_name="create_index_vectors_task",
        success_result_code="index_vectors_task_created",
        operation=lambda services, plan_id, turn_id: (
            services.create_index_vectors_task.execute(
                CreateIndexVectorsTaskInput(
                    plan_id=plan_id,
                    turn_id=turn_id,
                    document_id=tool_input.document_id,
                    sequence=tool_input.sequence,
                )
            )
        ),
    )
    if error is not None:
        return error
    return PlanningToolOutput(
        outcome="succeeded",
        result_code="index_vectors_task_created",
        message="文档索引 Task 已创建",
        retryable=False,
        resource_refs=[f"plan:{result.plan_id}", f"task:{result.task_id}"],
        plan_id=result.plan_id,
        task_id=result.task_id,
        status=result.status,
    )


create_index_vectors_task = function_tool(
    name_override="create_index_vectors_task",
    description_override="为当前 Plan 创建一项文档向量索引 Task。",
    failure_error_function=safe_tool_error_function,
)(create_index_vectors_task_handler)


def finalize_plan_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: FinalizePlanToolInput,
) -> PlanningToolOutput:
    _ = tool_input
    result, error = _execute(
        ctx,
        tool_name="finalize_plan",
        success_result_code="plan_finalized",
        operation=lambda services, plan_id, turn_id: (
            services.finalize_plan.execute(
                FinalizePlanInput(plan_id=plan_id, turn_id=turn_id)
            )
        ),
    )
    if error is not None:
        return error
    return PlanningToolOutput(
        outcome="succeeded",
        result_code="plan_finalized",
        message="Plan 已发布",
        retryable=False,
        resource_refs=[
            f"plan:{result.plan_id}",
            *(f"task:{task_id}" for task_id in result.task_ids),
        ],
        plan_id=result.plan_id,
        status=result.plan_status,
        task_ids=result.task_ids,
    )


finalize_plan = function_tool(
    name_override="finalize_plan",
    description_override="校验并原子发布当前 Plan 的全部 draft Tasks。",
    failure_error_function=safe_tool_error_function,
)(finalize_plan_handler)


def mark_plan_unsupported_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: MarkPlanUnsupportedToolInput,
) -> PlanningToolOutput:
    result, error = _execute(
        ctx,
        tool_name="mark_plan_unsupported",
        success_result_code="plan_marked_unsupported",
        operation=lambda services, plan_id, _turn_id: (
            services.mark_plan_unsupported.execute(
                MarkPlanUnsupportedInput(
                    plan_id=plan_id,
                    reason=tool_input.reason,
                )
            )
        ),
    )
    if error is not None:
        return error
    return PlanningToolOutput(
        outcome="succeeded",
        result_code="plan_marked_unsupported",
        message="Plan 已标记为不支持",
        retryable=False,
        resource_refs=[f"plan:{result.plan_id}"],
        plan_id=result.plan_id,
        status=result.status,
    )


mark_plan_unsupported = function_tool(
    name_override="mark_plan_unsupported",
    description_override="将当前无法支持的 Plan 标记为 unsupported 并记录原因。",
    failure_error_function=safe_tool_error_function,
)(mark_plan_unsupported_handler)
