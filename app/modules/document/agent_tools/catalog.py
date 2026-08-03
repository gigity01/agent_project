"""按 Agent 角色隔离的 Document Tool Catalog。"""

from dataclasses import dataclass
from typing import Literal

from agents.tool import FunctionTool

from app.agent_runtime.descriptors import ToolDescriptor
from app.agent_runtime.errors import ToolNotAvailableError
from app.modules.document.agent_tools.command_tools import (
    DOCUMENT_BUILD_CHUNKS_PERMISSION,
    DOCUMENT_INDEX_VECTORS_PERMISSION,
    DOCUMENT_PROCESS_PERMISSION,
    build_document_chunks,
    index_document_vectors,
    process_document,
)
from app.modules.document.agent_tools.query_tools import (
    DOCUMENT_READ_PERMISSION,
    get_document,
    get_document_chunk_statistics,
    get_document_pipeline_state,
    get_knowledge_base_statistics,
    list_child_chunks,
    list_document_artifacts,
    list_parent_blocks,
    search_document_artifacts,
    search_documents,
)


DocumentToolRole = Literal["document_collector", "document_executor"]


@dataclass(frozen=True)
class DocumentToolRegistration:
    tool: FunctionTool
    descriptor: ToolDescriptor


def _query_registration(
    tool: FunctionTool,
    description: str,
    *,
    resource_types: list[str] | None = None,
) -> DocumentToolRegistration:
    return DocumentToolRegistration(
        tool=tool,
        descriptor=ToolDescriptor(
            name=tool.name,
            description=description,
            operation_type="query",
            side_effect=False,
            idempotency="read_only",
            required_permissions=[DOCUMENT_READ_PERMISSION],
            resource_types=resource_types or ["document"],
            approval_required=False,
        ),
    )


def _command_registration(
    tool: FunctionTool,
    description: str,
    permission: str,
) -> DocumentToolRegistration:
    return DocumentToolRegistration(
        tool=tool,
        descriptor=ToolDescriptor(
            name=tool.name,
            description=description,
            operation_type="command",
            side_effect=True,
            idempotency="state_guarded",
            required_permissions=[permission],
            resource_types=["document"],
            approval_required=True,
        ),
    )


DOCUMENT_COLLECTOR_CATALOG = (
    _query_registration(get_document, "获取文档完整状态"),
    _query_registration(search_documents, "按高级条件查询文档"),
    _query_registration(
        get_document_pipeline_state,
        "获取文档处理、切块和索引状态",
    ),
    _query_registration(list_document_artifacts, "列出文档派生产物"),
    _query_registration(
        search_document_artifacts,
        "按高级条件查询文档派生产物",
        resource_types=["document", "document_artifact"],
    ),
    _query_registration(
        list_parent_blocks,
        "查询父级语义块明细",
        resource_types=["document", "parent_block"],
    ),
    _query_registration(
        list_child_chunks,
        "查询可向量化子块明细",
        resource_types=["document", "parent_block", "child_chunk"],
    ),
    _query_registration(
        get_document_chunk_statistics,
        "获取文档切块与向量状态统计",
        resource_types=["document", "parent_block", "child_chunk"],
    ),
    _query_registration(
        get_knowledge_base_statistics,
        "获取知识库文档与切块统计",
        resource_types=["knowledge_base", "document", "child_chunk"],
    ),
)

DOCUMENT_EXECUTOR_CATALOG = (
    _query_registration(get_document, "获取文档完整状态"),
    _command_registration(
        process_document,
        "处理或转换文档",
        DOCUMENT_PROCESS_PERMISSION,
    ),
    _command_registration(
        build_document_chunks,
        "构建文档父块和子块",
        DOCUMENT_BUILD_CHUNKS_PERMISSION,
    ),
    _command_registration(
        index_document_vectors,
        "生成并写入文档向量",
        DOCUMENT_INDEX_VECTORS_PERMISSION,
    ),
)

DOCUMENT_COLLECTOR_TOOLS = tuple(
    registration.tool for registration in DOCUMENT_COLLECTOR_CATALOG
)
DOCUMENT_EXECUTOR_TOOLS = tuple(
    registration.tool for registration in DOCUMENT_EXECUTOR_CATALOG
)


def _catalog_for_role(
    role: DocumentToolRole,
) -> tuple[DocumentToolRegistration, ...]:
    if role == "document_collector":
        return DOCUMENT_COLLECTOR_CATALOG
    if role == "document_executor":
        return DOCUMENT_EXECUTOR_CATALOG
    raise ToolNotAvailableError(f"未知 Document Tool 角色: {role}")


def get_document_tools(role: DocumentToolRole) -> tuple[FunctionTool, ...]:
    """只返回指定角色可见的 Tool。"""
    return tuple(item.tool for item in _catalog_for_role(role))


def get_document_tool_descriptors(
    role: DocumentToolRole,
) -> tuple[ToolDescriptor, ...]:
    """返回指定角色可供规划阶段读取的能力描述。"""
    return tuple(item.descriptor for item in _catalog_for_role(role))


def resolve_document_tool(
    role: DocumentToolRole,
    tool_name: str,
) -> FunctionTool:
    """仅在角色 Catalog 内解析 Tool，未注册能力不可调用。"""
    for item in _catalog_for_role(role):
        if item.descriptor.name == tool_name:
            return item.tool
    raise ToolNotAvailableError(
        f"Tool {tool_name!r} 未向角色 {role!r} 注册"
    )
