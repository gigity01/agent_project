"""Context 持久化事实只读 Function Tools。"""

from agents import RunContextWrapper, function_tool

from app.agent_runtime.audit import execute_audited_tool_call
from app.agent_runtime.context import AgentToolContext
from app.agent_runtime.errors import (
    ToolNotAvailableError,
    safe_tool_error_function,
)
from app.modules.context.agent_tools.schemas import (
    GetContextChainToolInput,
    GetContextChainToolOutput,
    GetConversationTurnToolInput,
    GetConversationTurnToolOutput,
    ListContextChainNodesToolInput,
    ListContextChainNodesToolOutput,
    ListContextChainResourcesToolInput,
    ListContextChainResourcesToolOutput,
    ListContextChainsToolInput,
    ListContextChainsToolOutput,
    ListContextRouteRecordsToolInput,
    ListContextRouteRecordsToolOutput,
    ListConversationTurnsToolInput,
    ListConversationTurnsToolOutput,
)
from app.modules.context.application.query_dto import (
    ContextChainNodeSearchQuery,
    ContextChainResourceSearchQuery,
    ContextChainSearchQuery,
    ContextRouteRecordSearchQuery,
    ConversationTurnSearchQuery,
)
from app.modules.context.application.query_service import ContextQueryService


CONTEXT_READ_PERMISSION = "context:read"


def _query_service(context: AgentToolContext) -> ContextQueryService:
    service = context.context_services.query_service
    if service is None:
        raise ToolNotAvailableError("Context 查询服务未注入")
    return service


def _get_conversation_turn(context: AgentToolContext, turn_id: str):
    use_case = context.context_services.get_conversation_turn
    if use_case is not None:
        return use_case.execute(turn_id)
    return _query_service(context).get_conversation_turn(turn_id)


def _list_conversation_turns(context: AgentToolContext, query):
    use_case = context.context_services.list_conversation_turns
    if use_case is not None:
        return use_case.execute(query)
    return _query_service(context).list_conversation_turns(query)


def _get_context_chain(context: AgentToolContext, chain_id: str):
    use_case = context.context_services.get_context_chain
    if use_case is not None:
        return use_case.execute(chain_id)
    return _query_service(context).get_context_chain(chain_id)


def _list_context_chains(context: AgentToolContext, query):
    use_case = context.context_services.list_context_chains
    if use_case is not None:
        return use_case.execute(query)
    return _query_service(context).list_context_chains(query)


def _list_context_chain_nodes(context: AgentToolContext, query):
    use_case = context.context_services.list_context_chain_nodes
    if use_case is not None:
        return use_case.execute(query)
    return _query_service(context).list_context_chain_nodes(query)


def _list_context_chain_resources(context: AgentToolContext, query):
    use_case = context.context_services.list_context_chain_resources
    if use_case is not None:
        return use_case.execute(query)
    return _query_service(context).list_context_chain_resources(query)


def _list_context_route_records(context: AgentToolContext, query):
    use_case = context.context_services.list_context_route_records
    if use_case is not None:
        return use_case.execute(query)
    return _query_service(context).list_context_route_records(query)


def get_conversation_turn_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: GetConversationTurnToolInput,
) -> GetConversationTurnToolOutput:
    resource_refs = [f"context_turn:{tool_input.turn_id}"]
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="get_conversation_turn",
        required_permissions=(CONTEXT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="conversation_turn_retrieved",
        operation=lambda: _get_conversation_turn(
            ctx.context,
            tool_input.turn_id,
        ),
    )
    if execution.error is not None:
        return GetConversationTurnToolOutput(**execution.error.__dict__)
    return GetConversationTurnToolOutput(
        outcome="succeeded",
        result_code="conversation_turn_retrieved",
        message="Conversation Turn 读取成功",
        retryable=False,
        resource_refs=resource_refs,
        turn=execution.value,
    )


get_conversation_turn = function_tool(
    name_override="get_conversation_turn",
    description_override="按 turn_id 获取已持久化的完整 Conversation Turn。",
    failure_error_function=safe_tool_error_function,
)(get_conversation_turn_handler)


def list_conversation_turns_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: ListConversationTurnsToolInput,
) -> ListConversationTurnsToolOutput:
    resource_refs = (
        [f"conversation:{tool_input.conversation_id}"]
        if tool_input.conversation_id
        else ["context_turn:*"]
    )
    query = ConversationTurnSearchQuery.model_validate(
        tool_input.model_dump()
    )
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="list_conversation_turns",
        required_permissions=(CONTEXT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="conversation_turns_listed",
        operation=lambda: _list_conversation_turns(ctx.context, query),
    )
    if execution.error is not None:
        return ListConversationTurnsToolOutput(
            **execution.error.__dict__,
            limit=tool_input.limit,
            offset=tool_input.offset,
        )
    result = execution.value
    assert result is not None
    return ListConversationTurnsToolOutput(
        outcome="succeeded",
        result_code="conversation_turns_listed",
        message="Conversation Turn 查询成功",
        retryable=False,
        resource_refs=resource_refs,
        turns=result.items,
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


list_conversation_turns = function_tool(
    name_override="list_conversation_turns",
    description_override="按 Conversation、状态和时间范围查询 Turn。",
    failure_error_function=safe_tool_error_function,
)(list_conversation_turns_handler)


def get_context_chain_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: GetContextChainToolInput,
) -> GetContextChainToolOutput:
    resource_refs = [f"context_chain:{tool_input.chain_id}"]
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="get_context_chain",
        required_permissions=(CONTEXT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="context_chain_retrieved",
        operation=lambda: _get_context_chain(
            ctx.context,
            tool_input.chain_id,
        ),
    )
    if execution.error is not None:
        return GetContextChainToolOutput(**execution.error.__dict__)
    return GetContextChainToolOutput(
        outcome="succeeded",
        result_code="context_chain_retrieved",
        message="Context Chain 读取成功",
        retryable=False,
        resource_refs=resource_refs,
        chain=execution.value,
    )


get_context_chain = function_tool(
    name_override="get_context_chain",
    description_override="按 chain_id 获取 Context Chain 基础状态。",
    failure_error_function=safe_tool_error_function,
)(get_context_chain_handler)


def list_context_chains_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: ListContextChainsToolInput,
) -> ListContextChainsToolOutput:
    resource_refs = (
        [f"conversation:{tool_input.conversation_id}"]
        if tool_input.conversation_id
        else ["context_chain:*"]
    )
    query = ContextChainSearchQuery.model_validate(tool_input.model_dump())
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="list_context_chains",
        required_permissions=(CONTEXT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="context_chains_listed",
        operation=lambda: _list_context_chains(ctx.context, query),
    )
    if execution.error is not None:
        return ListContextChainsToolOutput(
            **execution.error.__dict__,
            limit=tool_input.limit,
            offset=tool_input.offset,
        )
    result = execution.value
    assert result is not None
    return ListContextChainsToolOutput(
        outcome="succeeded",
        result_code="context_chains_listed",
        message="Context Chain 查询成功",
        retryable=False,
        resource_refs=resource_refs,
        chains=result.items,
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


list_context_chains = function_tool(
    name_override="list_context_chains",
    description_override="按 Conversation、归档状态和时间范围查询 Chain。",
    failure_error_function=safe_tool_error_function,
)(list_context_chains_handler)


def list_context_chain_nodes_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: ListContextChainNodesToolInput,
) -> ListContextChainNodesToolOutput:
    resource_refs = (
        [f"context_chain:{tool_input.chain_id}"]
        if tool_input.chain_id
        else ["context_chain_node:*"]
    )
    query = ContextChainNodeSearchQuery.model_validate(
        tool_input.model_dump()
    )
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="list_context_chain_nodes",
        required_permissions=(CONTEXT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="context_chain_nodes_listed",
        operation=lambda: _list_context_chain_nodes(ctx.context, query),
    )
    if execution.error is not None:
        return ListContextChainNodesToolOutput(
            **execution.error.__dict__,
            limit=tool_input.limit,
            offset=tool_input.offset,
        )
    result = execution.value
    assert result is not None
    return ListContextChainNodesToolOutput(
        outcome="succeeded",
        result_code="context_chain_nodes_listed",
        message="Context Chain Node 查询成功",
        retryable=False,
        resource_refs=resource_refs,
        nodes=result.items,
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


list_context_chain_nodes = function_tool(
    name_override="list_context_chain_nodes",
    description_override="按 Conversation、Chain、Turn 和时间范围查询 Node。",
    failure_error_function=safe_tool_error_function,
)(list_context_chain_nodes_handler)


def list_context_chain_resources_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: ListContextChainResourcesToolInput,
) -> ListContextChainResourcesToolOutput:
    resource_refs = (
        [f"context_chain:{tool_input.chain_id}"]
        if tool_input.chain_id
        else ["context_chain_resource:*"]
    )
    query = ContextChainResourceSearchQuery.model_validate(
        tool_input.model_dump()
    )
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="list_context_chain_resources",
        required_permissions=(CONTEXT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="context_chain_resources_listed",
        operation=lambda: _list_context_chain_resources(
            ctx.context,
            query,
        ),
    )
    if execution.error is not None:
        return ListContextChainResourcesToolOutput(
            **execution.error.__dict__,
            limit=tool_input.limit,
            offset=tool_input.offset,
        )
    result = execution.value
    assert result is not None
    return ListContextChainResourcesToolOutput(
        outcome="succeeded",
        result_code="context_chain_resources_listed",
        message="Context Chain Resource 查询成功",
        retryable=False,
        resource_refs=resource_refs,
        resources=result.items,
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


list_context_chain_resources = function_tool(
    name_override="list_context_chain_resources",
    description_override="按 Chain、资源类型、资源 ID 和有效状态查询资源。",
    failure_error_function=safe_tool_error_function,
)(list_context_chain_resources_handler)


def list_context_route_records_handler(
    ctx: RunContextWrapper[AgentToolContext],
    tool_input: ListContextRouteRecordsToolInput,
) -> ListContextRouteRecordsToolOutput:
    resource_refs = (
        [f"conversation:{tool_input.conversation_id}"]
        if tool_input.conversation_id
        else ["context_route_record:*"]
    )
    query = ContextRouteRecordSearchQuery.model_validate(
        tool_input.model_dump()
    )
    execution = execute_audited_tool_call(
        context=ctx.context,
        tool_name="list_context_route_records",
        required_permissions=(CONTEXT_READ_PERMISSION,),
        resource_refs=resource_refs,
        success_result_code="context_route_records_listed",
        operation=lambda: _list_context_route_records(ctx.context, query),
    )
    if execution.error is not None:
        return ListContextRouteRecordsToolOutput(
            **execution.error.__dict__,
            limit=tool_input.limit,
            offset=tool_input.offset,
        )
    result = execution.value
    assert result is not None
    return ListContextRouteRecordsToolOutput(
        outcome="succeeded",
        result_code="context_route_records_listed",
        message="Context RouteRecord 查询成功",
        retryable=False,
        resource_refs=resource_refs,
        route_records=result.items,
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


list_context_route_records = function_tool(
    name_override="list_context_route_records",
    description_override="按 Conversation、Turn、route_mode 和时间查询路由记录。",
    failure_error_function=safe_tool_error_function,
)(list_context_route_records_handler)
