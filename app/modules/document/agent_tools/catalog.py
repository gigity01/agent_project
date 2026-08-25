"""按 Agent 角色与 Capability 严格隔离的 Document Tool Catalog 注册表。

实现设计约束：
1. Document Collector Agent（取证阶段）：只分配只读 Query Tools（DOCUMENT_COLLECTOR_CATALOG），
   绝不暴露任何 Command Tools。
2. Document Executor Agents（执行阶段）：按 Task Capability 细粒度隔离
   - document.process: 只能看到受限查询 Tool + process_document 命令 Tool
   - document.build_chunks: 只能看到受限查询 Tool + build_document_chunks 命令 Tool
   - document.index_vectors: 只能看到受限查询 Tool + index_document_vectors 命令 Tool
3. 严格通过 ToolDescriptor 声明操作类型（query/command）、副作用、幂等性守卫与所需权限。
"""

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


# 支持的 Document Tool 角色定义
DocumentToolRole = Literal["document_collector"]

# 支持的 Document Executor 能力编码
DocumentExecutorCapability = Literal[
    "document.process",
    "document.build_chunks",
    "document.index_vectors",
]


@dataclass(frozen=True)
class DocumentToolRegistration:
    """单个 FunctionTool 及其运行时权限与元数据描述符的注册条目。

    Attributes:
        tool: OpenAI Agents SDK FunctionTool 实例。
        descriptor: 工具描述符（包含 operation_type, idempotency, permissions 等）。
    """

    tool: FunctionTool
    descriptor: ToolDescriptor


def _query_registration(
    tool: FunctionTool,
    description: str,
    *,
    resource_types: list[str] | None = None,
) -> DocumentToolRegistration:
    """构建只读查询类 Tool 的注册描述条目。

    Args:
        tool: FunctionTool 实例。
        description: 工具中文描述。
        resource_types: 涉及的资源类型列表（如 ['document', 'parent_block']）。

    Returns:
        DocumentToolRegistration 注册对象。
    """
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
    """构建状态守卫型命令类 Tool 的注册描述条目。

    Args:
        tool: FunctionTool 实例。
        description: 工具中文描述。
        permission: 该命令所需的唯一权限编码。

    Returns:
        DocumentToolRegistration 注册对象。
    """
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
            approval_required=False,
        ),
    )


# 1. Document Collector Agent（只读取证）可见的 Tool 目录
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

# 2. Document Process Executor 可见的受限 Tool 目录
DOCUMENT_PROCESS_EXECUTOR_CATALOG = (
    _query_registration(get_document, "获取文档完整状态"),
    _query_registration(
        get_document_pipeline_state,
        "获取文档处理、切块和索引状态",
    ),
    _command_registration(
        process_document,
        "处理或转换文档",
        DOCUMENT_PROCESS_PERMISSION,
    ),
)

# 3. Document Build Chunks Executor 可见的受限 Tool 目录
DOCUMENT_BUILD_CHUNKS_EXECUTOR_CATALOG = (
    _query_registration(get_document, "获取文档完整状态"),
    _query_registration(
        get_document_pipeline_state,
        "获取文档处理、切块和索引状态",
    ),
    _query_registration(
        get_document_chunk_statistics,
        "获取文档切块与向量状态统计",
        resource_types=["document", "parent_block", "child_chunk"],
    ),
    _command_registration(
        build_document_chunks,
        "构建文档父块和子块",
        DOCUMENT_BUILD_CHUNKS_PERMISSION,
    ),
)

# 4. Document Index Vectors Executor 可见的受限 Tool 目录
DOCUMENT_INDEX_VECTORS_EXECUTOR_CATALOG = (
    _query_registration(get_document, "获取文档完整状态"),
    _query_registration(
        get_document_pipeline_state,
        "获取文档处理、切块和索引状态",
    ),
    _query_registration(
        get_document_chunk_statistics,
        "获取文档切块与向量状态统计",
        resource_types=["document", "parent_block", "child_chunk"],
    ),
    _command_registration(
        index_document_vectors,
        "生成并写入文档向量",
        DOCUMENT_INDEX_VECTORS_PERMISSION,
    ),
)

# Capability -> Catalog 路由字典
DOCUMENT_EXECUTOR_CATALOGS: dict[
    str, tuple[DocumentToolRegistration, ...]
] = {
    "document.process": DOCUMENT_PROCESS_EXECUTOR_CATALOG,
    "document.build_chunks": DOCUMENT_BUILD_CHUNKS_EXECUTOR_CATALOG,
    "document.index_vectors": DOCUMENT_INDEX_VECTORS_EXECUTOR_CATALOG,
}

# Collector Tools 实例元组导出
DOCUMENT_COLLECTOR_TOOLS = tuple(
    registration.tool for registration in DOCUMENT_COLLECTOR_CATALOG
)


def _catalog_for_role(
    role: DocumentToolRole,
) -> tuple[DocumentToolRegistration, ...]:
    """根据角色获取对应的注册表元组。"""
    if role == "document_collector":
        return DOCUMENT_COLLECTOR_CATALOG
    raise ToolNotAvailableError(f"未知 Document Tool 角色: {role}")


def _catalog_for_executor(
    capability_code: str,
) -> tuple[DocumentToolRegistration, ...]:
    """根据 Capability 编码获取对应的 Executor 注册表元组。"""
    try:
        return DOCUMENT_EXECUTOR_CATALOGS[capability_code]
    except KeyError as exc:
        raise ToolNotAvailableError(
            f"未知 Document Executor Capability: {capability_code}"
        ) from exc


def get_document_tools(role: DocumentToolRole) -> tuple[FunctionTool, ...]:
    """只返回指定角色（如 document_collector）可见的 FunctionTool 列表。

    Args:
        role: 角色标识。

    Returns:
        FunctionTool 实例元组。
    """
    return tuple(item.tool for item in _catalog_for_role(role))


def get_document_tool_descriptors(
    role: DocumentToolRole,
) -> tuple[ToolDescriptor, ...]:
    """返回指定角色可供规划与审计读取的 ToolDescriptor 能力描述元组。

    Args:
        role: 角色标识。

    Returns:
        ToolDescriptor 元组。
    """
    return tuple(item.descriptor for item in _catalog_for_role(role))


def resolve_document_tool(
    role: DocumentToolRole,
    tool_name: str,
) -> FunctionTool:
    """仅在角色 Catalog 内按名称解析 Tool；未授权或未注册的能力禁止调用。

    Args:
        role: 角色标识。
        tool_name: 工具名称。

    Returns:
        FunctionTool 实例。

    Raises:
        ToolNotAvailableError: 工具未注册给该角色时抛出。
    """
    for item in _catalog_for_role(role):
        if item.descriptor.name == tool_name:
            return item.tool
    raise ToolNotAvailableError(
        f"Tool {tool_name!r} 未向角色 {role!r} 注册"
    )


def get_document_executor_tools(
    capability_code: str,
) -> tuple[FunctionTool, ...]:
    """只返回指定 Capability Executor 可见的受限 FunctionTool 列表。

    Args:
        capability_code: Capability 编码（如 'document.process'）。

    Returns:
        FunctionTool 实例元组。
    """
    return tuple(
        item.tool for item in _catalog_for_executor(capability_code)
    )


def get_document_executor_tool_descriptors(
    capability_code: str,
) -> tuple[ToolDescriptor, ...]:
    """返回指定 Capability Executor 的受限能力描述元组。

    Args:
        capability_code: Capability 编码。

    Returns:
        ToolDescriptor 元组。
    """
    return tuple(
        item.descriptor for item in _catalog_for_executor(capability_code)
    )


def resolve_document_executor_tool(
    capability_code: str,
    tool_name: str,
) -> FunctionTool:
    """仅在指定 Capability Catalog 内按名称解析 Tool。

    Args:
        capability_code: Capability 编码。
        tool_name: 工具名称。

    Returns:
        FunctionTool 实例。

    Raises:
        ToolNotAvailableError: 工具未注册给该 Capability 时抛出。
    """
    for item in _catalog_for_executor(capability_code):
        if item.descriptor.name == tool_name:
            return item.tool
    raise ToolNotAvailableError(
        f"Tool {tool_name!r} 未向 Capability {capability_code!r} 注册"
    )
