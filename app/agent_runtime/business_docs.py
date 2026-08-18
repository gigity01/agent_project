"""供 Agent 按需读取的项目业务说明。"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from agents import function_tool
from pydantic import BaseModel, ConfigDict, Field


BUSINESS_DOCS_ROOT = Path(__file__).resolve().parents[2] / "business_docs"
_TERM_PATTERN = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+")
SERVICE_MAP_PROMPT = """
本系统主要服务：

- Document Processing：文档处理、切块、向量索引和流水线状态查询。
- Context Management：Conversation、Turn、ContextChain、ResourceQueue 和 Context
  Selection。
- Operations：Workflow、Operation、Task Execution、Compensation、Recovery 和 Agent Tool
  审计查询。

Service Map 只帮助理解业务语境，不授予 Tool 权限，也不扩大 Context Selection 已确定的
历史 Read Set。
""".strip()


class SearchBusinessDocsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=8)


class BusinessDocMatch(BaseModel):
    document: str
    heading: str
    content: str


class SearchBusinessDocsOutput(BaseModel):
    query: str
    matches: list[BusinessDocMatch]


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


@lru_cache(maxsize=1)
def _load_business_doc_sections() -> tuple[BusinessDocMatch, ...]:
    if not BUSINESS_DOCS_ROOT.is_dir():
        raise RuntimeError(f"Business Docs 目录不存在: {BUSINESS_DOCS_ROOT}")

    sections: list[BusinessDocMatch] = []
    for path in sorted(BUSINESS_DOCS_ROOT.glob("*.md")):
        heading = path.stem
        body: list[str] = []

        def append_section() -> None:
            content = "\n".join(body).strip()
            if content:
                sections.append(
                    BusinessDocMatch(
                        document=path.name,
                        heading=heading,
                        content=content,
                    )
                )

        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#"):
                append_section()
                heading = line.lstrip("#").strip() or path.stem
                body = []
                continue
            body.append(line)
        append_section()

    if not sections:
        raise RuntimeError("Business Docs 目录中没有可查询的 Markdown 内容")
    return tuple(sections)


def load_service_map() -> str:
    """返回不依赖运行时文件加载的常驻短 Service Map。"""
    return SERVICE_MAP_PROMPT


def search_business_docs_handler(
    tool_input: SearchBusinessDocsInput,
) -> SearchBusinessDocsOutput:
    """按关键词返回最相关的 Markdown 章节。"""
    query = tool_input.query.casefold().strip()
    terms = _search_terms(query)
    ranked: list[tuple[int, BusinessDocMatch]] = []
    for section in _load_business_doc_sections():
        searchable = (
            f"{section.document}\n{section.heading}\n{section.content}"
        ).casefold()
        exact_match = bool(query and query in searchable)
        matched_terms = sum(1 for term in terms if term in searchable)
        required_terms = max(1, min(3, (len(terms) + 2) // 3))
        if exact_match or matched_terms >= required_terms:
            score = (100 if exact_match else 0) + matched_terms
            ranked.append((score, section))

    ranked.sort(
        key=lambda item: (
            -item[0],
            item[1].document,
            item[1].heading,
        )
    )
    return SearchBusinessDocsOutput(
        query=tool_input.query,
        matches=[section for _, section in ranked[: tool_input.limit]],
    )


search_business_docs = function_tool(
    name_override="search_business_docs",
    description_override=(
        "查询业务规则、前置事实、推荐查询路径和明确能力边界。"
    ),
)(search_business_docs_handler)
