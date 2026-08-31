"""Operations Collector 的只读 Tool 目录与元数据注册表。

定义 Operations 模块对外暴露给 Operations Collector Agent 的 Tool 注册元数据（ToolDescriptor）、
工具列表以及按名称动态查找 Tool 实例的解析函数。
"""

from dataclasses import dataclass

from agents.tool import FunctionTool

from app.agent_runtime.descriptors import ToolDescriptor
from app.agent_runtime.errors import ToolNotAvailableError
from app.modules.operations.agent_tools.query_tools import (
    OPERATIONS_READ_PERMISSION,
    get_agent_run_tool_timeline,
    get_document_execution_timeline,
    get_document_failure_timeline,
    get_document_operation_timeline,
    get_document_workflow_timeline,
    get_task_tool_timeline,
    query_agent_tool_audits,
    query_document_business_logs,
    query_document_log_events,
)


@dataclass(frozen=True)
class OperationsToolRegistration:
    """Operations Tool 注册元数据封装。

    Attributes:
        tool: FunctionTool 可执行实例。
        descriptor: 工具描述元数据（包含权限、幂等性、资源类型与审批策略等）。
    """

    tool: FunctionTool
    descriptor: ToolDescriptor


def _registration(
    tool: FunctionTool,
    description: str,
    resource_types: list[str],
) -> OperationsToolRegistration:
    """构造只读无副作用的 Operations 工具注册对象。

    Args:
        tool: FunctionTool 实例。
        description: 工具用途描述。
        resource_types: 工具操作涉及的资源类型列表。

    Returns:
        OperationsToolRegistration: 构造的注册条目。
    """
    return OperationsToolRegistration(
        tool=tool,
        descriptor=ToolDescriptor(
            name=tool.name,
            description=description,
            operation_type="query",
            side_effect=False,
            idempotency="read_only",
            required_permissions=[OPERATIONS_READ_PERMISSION],
            resource_types=resource_types,
            approval_required=False,
        ),
    )


# Operations Collector Agent 可用的完整工具目录注册列表
OPERATIONS_COLLECTOR_CATALOG = (
    _registration(
        query_document_log_events,
        "按统一关联字段查询文档业务事件",
        ["workflow", "operation", "document", "business_log"],
    ),
    _registration(
        get_document_operation_timeline,
        "获取一次文档阶段操作的事件时间线",
        ["operation", "document", "business_log"],
    ),
    _registration(
        get_document_workflow_timeline,
        "获取完整文档处理工作流事件时间线",
        ["workflow", "operation", "document", "business_log"],
    ),
    _registration(
        query_document_business_logs,
        "查询文档业务日志",
        ["document", "business_log"],
    ),
    _registration(
        get_document_execution_timeline,
        "获取文档执行时间线",
        ["document", "business_log"],
    ),
    _registration(
        get_document_failure_timeline,
        "获取文档失败时间线",
        ["document", "business_log"],
    ),
    _registration(
        query_agent_tool_audits,
        "查询 Agent Tool 审计",
        ["agent_run", "tool_audit"],
    ),
    _registration(
        get_task_tool_timeline,
        "获取 Task Tool 时间线",
        ["task", "tool_audit"],
    ),
    _registration(
        get_agent_run_tool_timeline,
        "获取 Agent Run Tool 时间线",
        ["agent_run", "tool_audit"],
    ),
)

# 仅包含 FunctionTool 实例的元组，供 Agent 初始化装配
OPERATIONS_COLLECTOR_TOOLS = tuple(
    registration.tool for registration in OPERATIONS_COLLECTOR_CATALOG
)


def get_operations_tool_descriptors() -> tuple[ToolDescriptor, ...]:
    """获取 Operations Collector 全部工具的 ToolDescriptor 元数据元组。

    Returns:
        tuple[ToolDescriptor, ...]: 工具描述符元组。
    """
    return tuple(
        registration.descriptor
        for registration in OPERATIONS_COLLECTOR_CATALOG
    )


def resolve_operations_tool(tool_name: str) -> FunctionTool:
    """根据 Tool 名称查找对应的 FunctionTool 实例。

    Args:
        tool_name: 待查找的工具名称字符串。

    Returns:
        FunctionTool: 匹配的工具实例。

    Raises:
        ToolNotAvailableError: 当指定的工具名称未注册时抛出。
    """
    for registration in OPERATIONS_COLLECTOR_CATALOG:
        if registration.tool.name == tool_name:
            return registration.tool
    raise ToolNotAvailableError(
        f"Tool {tool_name!r} 未向 Operations Collector 注册"
    )
