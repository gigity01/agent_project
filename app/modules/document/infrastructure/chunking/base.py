"""文档模块切块器的输入、输出数据结构和统一接口。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ChunkBuildInput:
    """切块器读取 cleaned 文件和处理产物元信息所需的统一输入。"""

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


class BaseChunker(ABC):
    """不同源文本格式的切块策略抽象基类。"""
    @abstractmethod
    def build(
        self,
        input_data: ChunkBuildInput,
    ) -> ChunkBuildResult:
        """读取 cleaned 文件并转换为父块和子块。"""
        raise NotImplementedError
