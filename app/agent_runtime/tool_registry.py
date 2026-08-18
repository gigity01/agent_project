"""现有 Collector Catalog 的统一只读视图。"""

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


EvidenceToolCatalog = Literal["document", "context", "operations"]
_TERM_PATTERN = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+")


class EvidenceToolView(BaseModel):
    catalog: EvidenceToolCatalog
    descriptor: ToolDescriptor


class ListEvidenceToolsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog: EvidenceToolCatalog | None = None


class FindEvidenceToolsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    catalog: EvidenceToolCatalog | None = None
    limit: int = Field(default=10, ge=1, le=25)


class EvidenceToolsOutput(BaseModel):
    tools: list[EvidenceToolView]
    authorization_note: str = (
        "Registry 只证明 Tool 已注册；实际查询范围仍由 AgentToolContext 限制。"
    )


def list_evidence_tool_views(
    catalog: EvidenceToolCatalog | None = None,
) -> tuple[EvidenceToolView, ...]:
    """动态投影三个 Collector Catalog，不保存第二份能力清单。"""
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
    return EvidenceToolsOutput(
        tools=list(list_evidence_tool_views(tool_input.catalog))
    )


def _search_terms(value: str) -> set[str]:
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
    query = tool_input.query.casefold().strip()
    terms = _search_terms(query)
    identifier_query = bool(re.fullmatch(r"[a-z0-9_]+", query))
    ranked: list[tuple[int, EvidenceToolView]] = []
    for view in list_evidence_tool_views(tool_input.catalog):
        descriptor = view.descriptor
        tool_name = descriptor.name.casefold()
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
