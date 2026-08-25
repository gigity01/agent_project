"""供 Agent 按需读取的项目业务说明与能力边界检索模块。

职责说明：
- 提供业务规则文档 (`business_docs/*.md`) 与服务映射 (`service_map.md`) 的加载与解析机制。
- 实现基于关键词（英文分词与中文 2-gram）的确定性轻量 Markdown 章节检索，避免依赖外部检索库。
- 向 Agent 暴露 `search_business_docs` Function Tool，供 Planner 与 Executor 动态查阅前置事实与规则。
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from agents import function_tool
from pydantic import BaseModel, ConfigDict, Field

# 业务规则文档根目录路径
BUSINESS_DOCS_ROOT = Path(__file__).resolve().parents[2] / "business_docs"
# 匹配英文字词/下划线标识符与中文字符片段的正则表达式
_TERM_PATTERN = re.compile(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+")


class SearchBusinessDocsInput(BaseModel):
    """业务文档检索工具输入模型。

    属性:
        query: 检索关键词或业务问题文本。
        limit: 返回最相关章节的最大数量（默认为 5，限制 1~8）。
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=8)


class BusinessDocMatch(BaseModel):
    """业务文档章节匹配结果模型。

    属性:
        document: 来源文件名（如 service_map.md）。
        heading: 章节标题或 Markdown 标题层级。
        content: 该章节的正文文本内容。
    """

    document: str
    heading: str
    content: str


class SearchBusinessDocsOutput(BaseModel):
    """业务文档检索工具输出模型。

    属性:
        query: 原始查询文本。
        matches: 按相关度降序排列的章节匹配项列表。
    """

    query: str
    matches: list[BusinessDocMatch]


def _search_terms(value: str) -> set[str]:
    """从检索文本中提取英文分词、下划线子词和中文 2-gram 关键词集合。

    参数:
        value: 待分词的查询字符串。

    返回:
        set[str]: 提取到的归一化关键词集合。
    """
    terms: set[str] = set()
    for token in _TERM_PATTERN.findall(value.casefold()):
        terms.add(token)
        if token.isascii():
            # 针对英文标识符拆分下划线子词
            terms.update(part for part in token.split("_") if part)
        elif len(token) > 2:
            # 针对较长中文片段生成 2-gram 滑动窗口词
            terms.update(
                token[index : index + 2]
                for index in range(len(token) - 1)
            )
    return {term for term in terms if term.strip()}


@lru_cache(maxsize=1)
def _load_business_doc_sections() -> tuple[BusinessDocMatch, ...]:
    """读取并缓存 business_docs 目录下的全部 Markdown 章节切片。

    以 Markdown 一级/二级标题 (#, ##) 作为章节切分边界。

    返回:
        tuple[BusinessDocMatch, ...]: 全部不可变的文档章节切片元组。

    异常:
        RuntimeError: 当业务文档目录不存在或无有效 Markdown 内容时抛出。
    """
    if not BUSINESS_DOCS_ROOT.is_dir():
        raise RuntimeError(f"Business Docs 目录不存在: {BUSINESS_DOCS_ROOT}")

    sections: list[BusinessDocMatch] = []
    for path in sorted(BUSINESS_DOCS_ROOT.glob("*.md")):
        heading = path.stem
        body: list[str] = []

        def append_section() -> None:
            """将累积的章节内容打包存入 sections 列表。"""
            content = "\n".join(body).strip()
            if content:
                sections.append(
                    BusinessDocMatch(
                        document=path.name,
                        heading=heading,
                        content=content,
                    )
                )

        # 逐行扫描 Markdown，按标题切分章节
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
    """从唯一 Markdown 事实源加载常驻短 Service Map。

    返回:
        str: Service Map Markdown 文件的完整文本内容。

    异常:
        RuntimeError: 当 service_map.md 无法读取或内容为空时抛出。
    """
    path = BUSINESS_DOCS_ROOT / "service_map.md"
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeError(f"Service Map 无法读取: {path}") from exc
    if not content:
        raise RuntimeError(f"Service Map 内容为空: {path}")
    return content


def search_business_docs_handler(
    tool_input: SearchBusinessDocsInput,
) -> SearchBusinessDocsOutput:
    """按关键词匹配与相关度打分，返回最相关的 Markdown 章节。

    打分规则：
    - 精确全匹配（query in searchable）加 100 分。
    - 匹配的分词数量累加得分。
    - 至少满足精确匹配或覆盖一定比例的检索分词。

    参数:
        tool_input: 检索输入参数，包含 query 与 limit。

    返回:
        SearchBusinessDocsOutput: 检索结果对象。
    """
    query = tool_input.query.casefold().strip()
    terms = _search_terms(query)
    ranked: list[tuple[int, BusinessDocMatch]] = []

    # 遍历所有已缓存的文档章节进行相关度打分
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

    # 按得分降序、文件名、标题字母序稳定排序
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


# 注册为 OpenAI Agents SDK 标准 Function Tool
search_business_docs = function_tool(
    name_override="search_business_docs",
    description_override=(
        "查询业务规则、前置事实、推荐查询路径和明确能力边界。"
    ),
)(search_business_docs_handler)
