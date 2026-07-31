"""文档模块不依赖外部基础设施的处理与切块模型。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProcessResult(BaseModel):
    """处理器写入清洗文件后返回的路径、统计与元数据。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    source_path: Path
    cleaned_path: Path
    source_type: str
    char_count: int = 0
    line_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarkdownConvertResult(BaseModel):
    """外部转换器生成 Markdown 后的内部结果。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    source_path: Path
    source_format: str
    markdown: str
    provider: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ChunkBuildInput:
    """切块器所需的 cleaned 文件和处理元信息。"""

    cleaned_path: Path
    document_title: str
    business_scene: str | None
    process_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParentBlockData:
    """尚未持久化的父级语义块数据。"""

    block_type: str
    title: str | None
    section_path: list[str] | None
    content: str
    block_index: int
    semantic_group_index: int
    segment_index: int


@dataclass
class ChildChunkData:
    """尚未持久化、可用于向量化的子块数据。"""

    content: str
    embedding_text: str
    chunk_index: int
    section_path: list[str] | None = None
    source_row_index: int | None = None
    chunk_type: str = "text"


@dataclass
class ChunkBuildResult:
    """一次切块产生的父块及其子块映射。"""

    parents: list[ParentBlockData]
    children_by_parent_index: dict[int, list[ChildChunkData]]
