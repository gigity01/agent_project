"""Operations Collector 的只读 Tool Catalog。"""

from dataclasses import dataclass

from agents.tool import FunctionTool

from app.agent_runtime.descriptors import ToolDescriptor
from app.agent_runtime.errors import ToolNotAvailableError
from app.modules.operations.agent_tools.query_tools import (
    OPERATIONS_READ_PERMISSION,
    get_agent_run_tool_timeline,
    get_document_execution_timeline,
    get_document_failure_timeline,
    get_task_tool_timeline,
    query_agent_tool_audits,
    query_document_business_logs,
)


@dataclass(frozen=True)
class OperationsToolRegistration:
    tool: FunctionTool
    descriptor: ToolDescriptor


def _registration(
    tool: FunctionTool,
    description: str,
    resource_types: list[str],
) -> OperationsToolRegistration:
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


OPERATIONS_COLLECTOR_CATALOG = (
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

OPERATIONS_COLLECTOR_TOOLS = tuple(
    registration.tool for registration in OPERATIONS_COLLECTOR_CATALOG
)


def get_operations_tool_descriptors() -> tuple[ToolDescriptor, ...]:
    return tuple(
        registration.descriptor
        for registration in OPERATIONS_COLLECTOR_CATALOG
    )


def resolve_operations_tool(tool_name: str) -> FunctionTool:
    for registration in OPERATIONS_COLLECTOR_CATALOG:
        if registration.tool.name == tool_name:
            return registration.tool
    raise ToolNotAvailableError(
        f"Tool {tool_name!r} 未向 Operations Collector 注册"
    )
