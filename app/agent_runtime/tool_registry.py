"""现有 Collector Catalog 的统一只读视图模块。

职责说明：
- 聚合 Document、Context、Operations 三个 Collector 目录的只读工具描述，向 Planner 与 GapHandler 提供动态查询接口。
- 提供 `list_evidence_tools` 与 `find_evidence_tools` 两个标准 Function Tool，支持按分类检索与分词模糊匹配。
- 保证单一事实源：不单独维护静态工具清单，而是从各模块的 catalog 动态读取投影。
"""

from __future__ import annotations

import re
from typing import Literal

from agents import function_tool
from pydantic import BaseModel, ConfigDict, Field

from app.agent_runtime.descriptors import ToolDescriptor
from app.modules.context.agent_tools.catalog import (
    get_context_tool_descriptors,
)
from app.modules.document.agent_tools.catalog import (
    get_document_tool_descriptors,
)
from app.modules.operations.agent_tools.catalog import (
    get_operations_tool_descriptors,
)

# 支持的 Evidence 工具目录分类类型
EvidenceToolCatalog = Literal["document", "context", "operations"]
_TERM_PATTERN = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+")


class EvidenceToolView(BaseModel):
    """Evidence Tool 视图模型。

    属性:
        catalog: 工具所属的目录分类（document、context 或 operations）。
        descriptor: 工具的元数据描述对象。
    """

    catalog: EvidenceToolCatalog
    descriptor: ToolDescriptor


class ListEvidenceToolsInput(BaseModel):
    """列出 Evidence Tool 的输入参数模型。

    属性:
        catalog: 可选的目录分类过滤器。若为空则返回所有分类的工具。
    """

    model_config = ConfigDict(extra="forbid")

    catalog: EvidenceToolCatalog | None = None


class FindEvidenceToolsInput(BaseModel):
    """按关键词查找 Evidence Tool 的输入参数模型。

    属性:
        query: 检索关键词或工具名称片段。
        catalog: 可选的目录分类过滤器。
        limit: 最多返回的结果数量（默认 10，限制 1~25）。
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    catalog: EvidenceToolCatalog | None = None
    limit: int = Field(default=10, ge=1, le=25)


class EvidenceToolsOutput(BaseModel):
    """Evidence Tool 列表/查询结果输出模型。

    属性:
        tools: 匹配的工具视图对象列表。
        authorization_note: 权限提示说明。
    """

    tools: list[EvidenceToolView]
    authorization_note: str = (
        "Registry 只证明 Tool 已注册；实际查询范围仍由 AgentToolContext 限制。"
    )


def list_evidence_tool_views(
    catalog: EvidenceToolCatalog | None = None,
) -> tuple[EvidenceToolView, ...]:
    """动态投影汇总三个 Collector Catalog 的工具元数据描述。

    参数:
        catalog: 可选的分类过滤条件。

    返回:
        tuple[EvidenceToolView, ...]: 不可变的工具视图元组。
    """
    sources: tuple[
        tuple[EvidenceToolCatalog, tuple[ToolDescriptor, ...]], ...
    ] = (
        (
            "document",
            get_document_tool_descriptors("document_collector"),
        ),
        ("context", get_context_tool_descriptors()),
        ("operations", get_operations_tool_descriptors()),
    )
    return tuple(
        EvidenceToolView(catalog=source, descriptor=descriptor)
        for source, descriptors in sources
        if catalog is None or source == catalog
        for descriptor in descriptors
    )


def list_evidence_tools_handler(
    tool_input: ListEvidenceToolsInput,
) -> EvidenceToolsOutput:
    """处理列出 Evidence Tool 的工具调用请求。

    参数:
        tool_input: 列出工具的输入参数。

    返回:
        EvidenceToolsOutput: 工具视图列表。
    """
    return EvidenceToolsOutput(
        tools=list(list_evidence_tool_views(tool_input.catalog))
    )


def _search_terms(value: str) -> set[str]:
    """提取搜索词的英文、下划线分词与中文 2-gram 关键词集合。

    参数:
        value: 搜索词文本。

    返回:
        set[str]: 关键词集合。
    """
    terms: set[str] = set()
    for token in _TERM_PATTERN.findall(value.casefold()):
        terms.add(token)
        if token.isascii():
            terms.update(part for part in token.split("_") if part)
        elif len(token) > 2:
            terms.update(
                token[index : index + 2]
                for index in range(len(token) - 1)
            )
    return {term for term in terms if term.strip()}


def find_evidence_tools_handler(
    tool_input: FindEvidenceToolsInput,
) -> EvidenceToolsOutput:
    """按关键词与相关度打分匹配已注册的 Evidence Tool。

    打分规则：
    - 精确匹配工具名得 100 分。
    - 工具名/描述/资源类型包含完整查询词得 50 分。
    - 匹配分词数量累加得分。

    参数:
        tool_input: 查找工具的输入参数。

    返回:
        EvidenceToolsOutput: 按相关度降序排列的工具视图列表。
    """
    query = tool_input.query.casefold().strip()
    terms = _search_terms(query)
    identifier_query = bool(re.fullmatch(r"[a-z0-9_]+", query))
    ranked: list[tuple[int, EvidenceToolView]] = []

    for view in list_evidence_tool_views(tool_input.catalog):
        descriptor = view.descriptor
        tool_name = descriptor.name.casefold()
        # 若为严格标识符查询且未在工具名中出现，则跳过
        if identifier_query and query not in tool_name:
            continue
        searchable = "\n".join(
            [
                descriptor.name,
                descriptor.description,
                *descriptor.resource_types,
            ]
        ).casefold()
        score = 100 if query == tool_name else 0
        score += 50 if query and query in searchable else 0
        score += sum(1 for term in terms if term in searchable)
        if score:
            ranked.append((score, view))

    # 按相关度得分降序、catalog、工具名升序排序
    ranked.sort(
        key=lambda item: (
            -item[0],
            item[1].catalog,
            item[1].descriptor.name,
        )
    )
    return EvidenceToolsOutput(
        tools=[view for _, view in ranked[: tool_input.limit]]
    )


# 注册为 OpenAI Agents SDK 标准 Function Tool
list_evidence_tools = function_tool(
    name_override="list_evidence_tools",
    description_override=(
        "列出当前代码真实注册的 Document、Context 或 Operations Evidence Tools。"
    ),
)(list_evidence_tools_handler)

find_evidence_tools = function_tool(
    name_override="find_evidence_tools",
    description_override=(
        "按 Tool 名、描述和资源类型查找当前真实注册的 Evidence Tools。"
    ),
)(find_evidence_tools_handler)
