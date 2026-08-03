"""业务日志和 Tool 审计只读 Function Tools。"""

from agents import RunContextWrapper, function_tool

from app.agent_runtime.audit import execute_audited_tool_call
from app.agent_runtime.context import AgentToolContext
from app.agent_runtime.errors import (
    ToolNotAvailableError,
    safe_tool_error_function,
)
from app.modules.operations.agent_tools.schemas import (
    GetAgentRunToolTimelineToolInput,
    GetDocumentExecutionTimelineToolInput,
    GetDocumentExecutionTimelineToolOutput,
    GetDocumentFailureTimelineToolInput,
    GetDocumentFailureTimelineToolOutput,
    GetTaskToolTimelineToolInput,
    QueryAgentToolAuditsToolInput,
    QueryAgentToolAuditsToolOutput,
    QueryDocumentBusinessLogsToolInput,
    QueryDocumentBusinessLogsToolOutput,
    ToolTimelineToolOutput,
)
from app.modules.operations.application.dto import (
    AgentToolAuditQuery,
    DocumentBusinessLogQuery,
    DocumentTimelineQuery,
    ToolTimelineQuery,
)
from app.modules.operations.application.query_service import OperationsQueryService


OPERATIONS_READ_PERMISSION = "operations:read"


def _query_service(context: AgentToolContext) -> OperationsQueryService:
    service = context.operations_services.query_service
    if service is None:
        raise ToolNotAvailableError("Operations 查询服务未注入")
    return service


def query_document_business_logs_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: QueryDocumentBusinessLogsToolInput,
) -> QueryDocumentBusinessLogsToolOutput:
    resource_refs = [
        *(f"document:{item}" for item in tool_input.document_ids),
        *(f"knowledge_base:{item}" for item in tool_input.kb_ids),
    ] or ["document_business_log:*"]
    query = DocumentBusinessLogQuery.model_validate(tool_input.model_dump())
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="query_document_business_logs",
        required_permissions=(OPERATIONS_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_business_logs_queried",
        operation=lambda: _query_service(
            ctx.context
        ).query_document_business_logs(query),
    )
    if execution.error is not None:
        return QueryDocumentBusinessLogsToolOutput(
            **execution.error.__dict__
        )
    result = execution.value
    assert result is not None
    return QueryDocumentBusinessLogsToolOutput(
        outcome="succeeded",
        result_code="document_business_logs_queried",
        message="文档业务日志查询成功",
        retryable=False,
        resource_refs=resource_refs,
        events=result.items,
        next_cursor=result.next_cursor,
    )


query_document_business_logs = function_tool(
    name_override="query_document_business_logs",
    description_override="按文档、知识库、阶段、事件、级别和时间查询业务日志。",
    failure_error_function=safe_tool_error_function,
)(query_document_business_logs_handler)


def get_document_execution_timeline_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: GetDocumentExecutionTimelineToolInput,
) -> GetDocumentExecutionTimelineToolOutput:
    resource_refs = [f"document:{tool_input.document_id}"]
    query = DocumentTimelineQuery.model_validate(tool_input.model_dump())
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="get_document_execution_timeline",
        required_permissions=(OPERATIONS_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_execution_timeline_retrieved",
        operation=lambda: _query_service(
            ctx.context
        ).get_document_execution_timeline(query),
    )
    if execution.error is not None:
        return GetDocumentExecutionTimelineToolOutput(
            **execution.error.__dict__
        )
    return GetDocumentExecutionTimelineToolOutput(
        outcome="succeeded",
        result_code="document_execution_timeline_retrieved",
        message="文档执行时间线读取成功",
        retryable=False,
        resource_refs=resource_refs,
        timeline=execution.value,
    )


get_document_execution_timeline = function_tool(
    name_override="get_document_execution_timeline",
    description_override="按时间合并文档 upload、process、chunk、index 事件。",
    failure_error_function=safe_tool_error_function,
)(get_document_execution_timeline_handler)


def get_document_failure_timeline_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: GetDocumentFailureTimelineToolInput,
) -> GetDocumentFailureTimelineToolOutput:
    resource_refs = [f"document:{tool_input.document_id}"]
    query = DocumentTimelineQuery.model_validate(tool_input.model_dump())
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="get_document_failure_timeline",
        required_permissions=(OPERATIONS_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_failure_timeline_retrieved",
        operation=lambda: _query_service(
            ctx.context
        ).get_document_failure_timeline(query),
    )
    if execution.error is not None:
        return GetDocumentFailureTimelineToolOutput(
            **execution.error.__dict__
        )
    return GetDocumentFailureTimelineToolOutput(
        outcome="succeeded",
        result_code="document_failure_timeline_retrieved",
        message="文档失败时间线读取成功",
        retryable=False,
        resource_refs=resource_refs,
        timeline=execution.value,
    )


get_document_failure_timeline = function_tool(
    name_override="get_document_failure_timeline",
    description_override="获取文档失败阶段、错误摘要和状态变化时间线。",
    failure_error_function=safe_tool_error_function,
)(get_document_failure_timeline_handler)


def query_agent_tool_audits_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: QueryAgentToolAuditsToolInput,
) -> QueryAgentToolAuditsToolOutput:
    resource_refs = ["agent_tool_audit:*"]
    query = AgentToolAuditQuery.model_validate(tool_input.model_dump())
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="query_agent_tool_audits",
        required_permissions=(OPERATIONS_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="agent_tool_audits_queried",
        operation=lambda: _query_service(
            ctx.context
        ).query_agent_tool_audits(query),
    )
    if execution.error is not None:
        return QueryAgentToolAuditsToolOutput(
            **execution.error.__dict__
        )
    result = execution.value
    assert result is not None
    return QueryAgentToolAuditsToolOutput(
        outcome="succeeded",
        result_code="agent_tool_audits_queried",
        message="Agent Tool 审计查询成功",
        retryable=False,
        resource_refs=resource_refs,
        audits=result.items,
        next_cursor=result.next_cursor,
    )


query_agent_tool_audits = function_tool(
    name_override="query_agent_tool_audits",
    description_override="按 Agent、Tool、Task、Turn、结果和时间查询 Tool 审计。",
    failure_error_function=safe_tool_error_function,
)(query_agent_tool_audits_handler)


def get_task_tool_timeline_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: GetTaskToolTimelineToolInput,
) -> ToolTimelineToolOutput:
    resource_refs = [f"task:{tool_input.task_id}"]
    query = ToolTimelineQuery(
        identifier=tool_input.task_id,
        agent_names=tool_input.agent_names,
        tool_names=tool_input.tool_names,
        created_from=tool_input.created_from,
        created_to=tool_input.created_to,
        limit=tool_input.limit,
    )
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="get_task_tool_timeline",
        required_permissions=(OPERATIONS_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="task_tool_timeline_retrieved",
        operation=lambda: _query_service(ctx.context).get_task_tool_timeline(
            query
        ),
    )
    if execution.error is not None:
        return ToolTimelineToolOutput(
            **execution.error.__dict__,
            identifier=tool_input.task_id,
        )
    result = execution.value
    assert result is not None
    return ToolTimelineToolOutput(
        outcome="succeeded",
        result_code="task_tool_timeline_retrieved",
        message="Task Tool 时间线读取成功",
        retryable=False,
        resource_refs=resource_refs,
        identifier=result.identifier,
        invocations=result.invocations,
        truncated=result.truncated,
    )


get_task_tool_timeline = function_tool(
    name_override="get_task_tool_timeline",
    description_override="获取一个 Task 的完整 Tool 调用时间线。",
    failure_error_function=safe_tool_error_function,
)(get_task_tool_timeline_handler)


def get_agent_run_tool_timeline_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: GetAgentRunToolTimelineToolInput,
) -> ToolTimelineToolOutput:
    resource_refs = [f"agent_run:{tool_input.agent_run_id}"]
    query = ToolTimelineQuery(
        identifier=tool_input.agent_run_id,
        agent_names=tool_input.agent_names,
        tool_names=tool_input.tool_names,
        created_from=tool_input.created_from,
        created_to=tool_input.created_to,
        limit=tool_input.limit,
    )
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="get_agent_run_tool_timeline",
        required_permissions=(OPERATIONS_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="agent_run_tool_timeline_retrieved",
        operation=lambda: _query_service(
            ctx.context
        ).get_agent_run_tool_timeline(query),
    )
    if execution.error is not None:
        return ToolTimelineToolOutput(
            **execution.error.__dict__,
            identifier=tool_input.agent_run_id,
        )
    result = execution.value
    assert result is not None
    return ToolTimelineToolOutput(
        outcome="succeeded",
        result_code="agent_run_tool_timeline_retrieved",
        message="Agent Run Tool 时间线读取成功",
        retryable=False,
        resource_refs=resource_refs,
        identifier=result.identifier,
        invocations=result.invocations,
        truncated=result.truncated,
    )


get_agent_run_tool_timeline = function_tool(
    name_override="get_agent_run_tool_timeline",
    description_override="获取一次 Agent Run 的完整 Tool 调用时间线。",
    failure_error_function=safe_tool_error_function,
)(get_agent_run_tool_timeline_handler)
