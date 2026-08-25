"""业务日志和 Tool 审计只读 Function Tools。

为 Operations Collector Agent 提供一套受控的、只读的 Agent-as-Tool 函数工具集。
通过 execute_audited_tool_call 包装所有查询调用，记录审计轨迹并校验 operations:read 权限。
"""

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
    GetDocumentOperationTimelineToolInput,
    GetDocumentOperationTimelineToolOutput,
    GetDocumentWorkflowTimelineToolInput,
    GetDocumentWorkflowTimelineToolOutput,
    GetTaskToolTimelineToolInput,
    QueryAgentToolAuditsToolInput,
    QueryAgentToolAuditsToolOutput,
    QueryDocumentBusinessLogsToolInput,
    QueryDocumentBusinessLogsToolOutput,
    QueryDocumentLogEventsToolInput,
    QueryDocumentLogEventsToolOutput,
    ToolTimelineToolOutput,
)
from app.modules.operations.application.dto import (
    AgentToolAuditQuery,
    DocumentBusinessLogQuery,
    DocumentTimelineQuery,
    DocumentOperationTimelineQuery,
    DocumentWorkflowTimelineQuery,
    ToolTimelineQuery,
)
from app.modules.operations.application.query_service import OperationsQueryService


# Operations 模块只读查询所需的基础权限名称
OPERATIONS_READ_PERMISSION = "operations:read"


def _query_service(context: AgentToolContext) -> OperationsQueryService:
    """从 Agent 上下文中提取 OperationsQueryService 实例。

    Args:
        context: 当前 Agent 工具运行时上下文。

    Returns:
        OperationsQueryService: 查询服务实例。

    Raises:
        ToolNotAvailableError: 当查询服务未在上下文中正确注入时抛出。
    """
    service = context.operations_services.query_service
    if service is None:
        raise ToolNotAvailableError("Operations 查询服务未注入")
    return service


def _query_document_log_events(context: AgentToolContext, query):
    """优先使用显式 Use Case 执行文档日志事件查询，若未注入则回退到 QueryService。"""
    use_case = context.operations_services.query_document_log_events
    if use_case is not None:
        return use_case.execute(query)
    return _query_service(context).query_document_business_logs(query)


def _get_document_operation_timeline(context: AgentToolContext, query):
    """优先使用显式 Use Case 获取单次操作时间线，若未注入则回退到 QueryService。"""
    use_case = context.operations_services.get_document_operation_timeline
    if use_case is not None:
        return use_case.execute(query)
    return _query_service(context).get_document_operation_timeline(query)


def _get_document_workflow_timeline(context: AgentToolContext, query):
    """优先使用显式 Use Case 获取工作流时间线，若未注入则回退到 QueryService。"""
    use_case = context.operations_services.get_document_workflow_timeline
    if use_case is not None:
        return use_case.execute(query)
    return _query_service(context).get_document_workflow_timeline(query)


def query_document_log_events_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: QueryDocumentLogEventsToolInput,
) -> QueryDocumentLogEventsToolOutput:
    """处理文档业务日志事件查询工具调用。

    根据 workflow_id, operation_id, document_id 等关联维度查询统一关联日志。

    Args:
        ctx: Agent 运行时上下文包装器。
        tool_input: 查询输入参数。

    Returns:
        QueryDocumentLogEventsToolOutput: 包含匹配事件列表与游标的标准工具响应。
    """
    # 构造资源引用集合，用于审计追踪
    resource_refs = [
        *(f"workflow:{item}" for item in tool_input.workflow_ids),
        *(f"operation:{item}" for item in tool_input.operation_ids),
        *(f"document:{item}" for item in tool_input.document_ids),
    ] or ["document_log_event:*"]
    query = DocumentBusinessLogQuery.model_validate(tool_input.model_dump())

    # 执行审计化 Tool 调用
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="query_document_log_events",
        required_permissions=(OPERATIONS_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_log_events_queried",
        operation=lambda: _query_document_log_events(ctx.context, query),
    )
    if execution.error is not None:
        return QueryDocumentLogEventsToolOutput(**execution.error.__dict__)
    result = execution.value
    assert result is not None
    return QueryDocumentLogEventsToolOutput(
        outcome="succeeded",
        result_code="document_log_events_queried",
        message="文档业务事件查询成功",
        retryable=False,
        resource_refs=resource_refs,
        events=result.items,
        next_cursor=result.next_cursor,
    )


query_document_log_events = function_tool(
    name_override="query_document_log_events",
    description_override=(
        "按 workflow、operation、attempt、文档、阶段和时间查询业务事件。"
    ),
    failure_error_function=safe_tool_error_function,
)(query_document_log_events_handler)


def get_document_operation_timeline_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: GetDocumentOperationTimelineToolInput,
) -> GetDocumentOperationTimelineToolOutput:
    """处理单次文档操作时间线查询工具调用。

    按 operation_id 提取一次阶段操作的完整事件时间序列。

    Args:
        ctx: Agent 运行时上下文包装器。
        tool_input: 包含 operation_id 的输入参数。

    Returns:
        GetDocumentOperationTimelineToolOutput: 包含操作事件时间线的标准响应。
    """
    resource_refs = [f"operation:{tool_input.operation_id}"]
    query = DocumentOperationTimelineQuery.model_validate(
        tool_input.model_dump()
    )
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="get_document_operation_timeline",
        required_permissions=(OPERATIONS_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_operation_timeline_retrieved",
        operation=lambda: _get_document_operation_timeline(
            ctx.context,
            query,
        ),
    )
    if execution.error is not None:
        return GetDocumentOperationTimelineToolOutput(
            **execution.error.__dict__
        )
    return GetDocumentOperationTimelineToolOutput(
        outcome="succeeded",
        result_code="document_operation_timeline_retrieved",
        message="文档操作时间线读取成功",
        retryable=False,
        resource_refs=resource_refs,
        timeline=execution.value,
    )


get_document_operation_timeline = function_tool(
    name_override="get_document_operation_timeline",
    description_override="按 operation_id 获取一次阶段操作的完整事件时间线。",
    failure_error_function=safe_tool_error_function,
)(get_document_operation_timeline_handler)


def get_document_workflow_timeline_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: GetDocumentWorkflowTimelineToolInput,
) -> GetDocumentWorkflowTimelineToolOutput:
    """处理完整文档工作流时间线查询工具调用。

    按 workflow_id 提取跨阶段、跨重试的完整事件流。

    Args:
        ctx: Agent 运行时上下文包装器。
        tool_input: 包含 workflow_id 的输入参数。

    Returns:
        GetDocumentWorkflowTimelineToolOutput: 包含工作流时间线的标准响应。
    """
    resource_refs = [f"workflow:{tool_input.workflow_id}"]
    query = DocumentWorkflowTimelineQuery.model_validate(
        tool_input.model_dump()
    )
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="get_document_workflow_timeline",
        required_permissions=(OPERATIONS_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="document_workflow_timeline_retrieved",
        operation=lambda: _get_document_workflow_timeline(
            ctx.context,
            query,
        ),
    )
    if execution.error is not None:
        return GetDocumentWorkflowTimelineToolOutput(
            **execution.error.__dict__
        )
    return GetDocumentWorkflowTimelineToolOutput(
        outcome="succeeded",
        result_code="document_workflow_timeline_retrieved",
        message="文档工作流时间线读取成功",
        retryable=False,
        resource_refs=resource_refs,
        timeline=execution.value,
    )


get_document_workflow_timeline = function_tool(
    name_override="get_document_workflow_timeline",
    description_override="按 workflow_id 获取跨阶段和重试的完整事件时间线。",
    failure_error_function=safe_tool_error_function,
)(get_document_workflow_timeline_handler)


def query_document_business_logs_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: QueryDocumentBusinessLogsToolInput,
) -> QueryDocumentBusinessLogsToolOutput:
    """处理文档业务日志通用查询工具调用。

    按文档、知识库、阶段、事件、级别和时间范围筛选日志。

    Args:
        ctx: Agent 运行时上下文包装器。
        tool_input: 查询输入参数。

    Returns:
        QueryDocumentBusinessLogsToolOutput: 包含日志事件列表与游标的标准响应。
    """
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
    """处理单篇文档生命周期执行时间线查询工具调用。

    合并并按时间排列文档从 upload 到 process、chunk、index 的全过程事件。

    Args:
        ctx: Agent 运行时上下文包装器。
        tool_input: 包含 document_id 的输入参数。

    Returns:
        GetDocumentExecutionTimelineToolOutput: 包含执行时间线的标准响应。
    """
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
    """处理单篇文档失败历史时间线查询工具调用。

    提取文档在各流水线阶段发生的错误、失败类型和状态流转历史。

    Args:
        ctx: Agent 运行时上下文包装器。
        tool_input: 包含 document_id 的输入参数。

    Returns:
        GetDocumentFailureTimelineToolOutput: 包含失败事件时间线的标准响应。
    """
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
    """处理 Agent Tool 审计日志查询工具调用。

    支持按 Agent、Tool、Task、Turn、结果码以及时间过滤审计事件。

    Args:
        ctx: Agent 运行时上下文包装器。
        tool_input: 包含审计查询条件的输入参数。

    Returns:
        QueryAgentToolAuditsToolOutput: 包含审计列表与游标的标准响应。
    """
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
    """处理 Task 级别的 Tool 调用时间线查询工具调用。

    聚合并配对指定 Task 下的所有 Tool 调用的开始、结束和结果状态。

    Args:
        ctx: Agent 运行时上下文包装器。
        tool_input: 包含 task_id 的输入参数。

    Returns:
        ToolTimelineToolOutput: 包含调用时间线的标准响应。
    """
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
    """处理 Agent Run 级别的 Tool 调用时间线查询工具调用。

    聚合并配对指定一次 Agent 运行会话下的全部 Tool 调用时间线。

    Args:
        ctx: Agent 运行时上下文包装器。
        tool_input: 包含 agent_run_id 的输入参数。

    Returns:
        ToolTimelineToolOutput: 包含调用时间线的标准响应。
    """
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
