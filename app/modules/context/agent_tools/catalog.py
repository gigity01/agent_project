"""Context Collector 的只读 Tool 目录与元数据注册。"""

from __future__ import annotations

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
    list_context_selection_records,
    list_conversation_turns,
)


@dataclass(frozen=True)
class ContextToolRegistration:
    """Context Tool 及其运行时描述符元数据对。

    Attributes:
        tool: OpenAI Agents SDK FunctionTool 实例。
        descriptor: 统一运行时审计与权限描述符 ToolDescriptor。
    """

    tool: FunctionTool
    descriptor: ToolDescriptor


def _registration(
    tool: FunctionTool,
    description: str,
    resource_types: list[str],
) -> ContextToolRegistration:
    """构造 Context 只读 Tool 注册对象。

    Args:
        tool: FunctionTool 实例。
        description: 工具功能描述。
        resource_types: 涉及的资源类型标识列表。

    Returns:
        ContextToolRegistration: 包装后的注册项。
    """
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
        list_context_selection_records,
        "查询 Context SelectionRecord",
        ["conversation", "turn", "selection_record"],
    ),
)

CONTEXT_COLLECTOR_TOOLS = tuple(
    registration.tool for registration in CONTEXT_COLLECTOR_CATALOG
)


def get_context_tool_descriptors() -> tuple[ToolDescriptor, ...]:
    """获取所有 Context 只读 Tool 的描述符元数据列表。

    Returns:
        tuple[ToolDescriptor, ...]: 工具描述符元组。
    """
    return tuple(
        registration.descriptor
        for registration in CONTEXT_COLLECTOR_CATALOG
    )


def resolve_context_tool(tool_name: str) -> FunctionTool:
    """根据工具名称解析对应的 Context FunctionTool 实例。

    Args:
        tool_name: 工具名称字符串。

    Returns:
        FunctionTool: 匹配的工具实例。

    Raises:
        ToolNotAvailableError: 工具未注册时抛出。
    """
    for registration in CONTEXT_COLLECTOR_CATALOG:
        if registration.tool.name == tool_name:
            return registration.tool
    raise ToolNotAvailableError(
        f"Tool {tool_name!r} 未向 Context Collector 注册"
    )
