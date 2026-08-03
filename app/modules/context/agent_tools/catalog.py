"""Context Collector 的只读 Tool Catalog。"""

from dataclasses import dataclass

from agents.tool import FunctionTool

from app.agent_runtime.descriptors import ToolDescriptor
from app.agent_runtime.errors import ToolNotAvailableError
from app.modules.context.agent_tools.query_tools import (
    CONTEXT_READ_PERMISSION,
    get_context_chain,
    get_conversation_turn,
    list_context_chain_nodes,
    list_context_chain_resources,
    list_context_chains,
    list_context_route_records,
    list_conversation_turns,
)


@dataclass(frozen=True)
class ContextToolRegistration:
    tool: FunctionTool
    descriptor: ToolDescriptor


def _registration(
    tool: FunctionTool,
    description: str,
    resource_types: list[str],
) -> ContextToolRegistration:
    return ContextToolRegistration(
        tool=tool,
        descriptor=ToolDescriptor(
            name=tool.name,
            description=description,
            operation_type="query",
            side_effect=False,
            idempotency="read_only",
            required_permissions=[CONTEXT_READ_PERMISSION],
            resource_types=resource_types,
            approval_required=False,
        ),
    )


CONTEXT_COLLECTOR_CATALOG = (
    _registration(get_conversation_turn, "获取 Conversation Turn", ["turn"]),
    _registration(list_conversation_turns, "查询 Conversation Turn", ["turn"]),
    _registration(get_context_chain, "获取 Context Chain", ["chain"]),
    _registration(list_context_chains, "查询 Context Chain", ["chain"]),
    _registration(
        list_context_chain_nodes,
        "查询 Context Chain Node",
        ["chain", "turn", "node"],
    ),
    _registration(
        list_context_chain_resources,
        "查询 Context Chain Resource",
        ["chain", "resource"],
    ),
    _registration(
        list_context_route_records,
        "查询 Context RouteRecord",
        ["conversation", "turn", "route_record"],
    ),
)

CONTEXT_COLLECTOR_TOOLS = tuple(
    registration.tool for registration in CONTEXT_COLLECTOR_CATALOG
)


def get_context_tool_descriptors() -> tuple[ToolDescriptor, ...]:
    return tuple(
        registration.descriptor
        for registration in CONTEXT_COLLECTOR_CATALOG
    )


def resolve_context_tool(tool_name: str) -> FunctionTool:
    for registration in CONTEXT_COLLECTOR_CATALOG:
        if registration.tool.name == tool_name:
            return registration.tool
    raise ToolNotAvailableError(
        f"Tool {tool_name!r} 未向 Context Collector 注册"
    )
