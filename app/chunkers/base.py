"""定义文本切块器的输入、输出数据结构和统一接口。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass



@dataclass
class ParentBlockData:
    """尚未持久化的父级语义块数据。"""
    block_type: str
    title: str | None
    section_path: list[str] | None
    content: str
    block_index: int
    metadata: dict | None = None

@dataclass
class ChildChunkData:
    """尚未持久化、可用于向量化的子块数据。"""
    content: str
    embedding_text: str
    chunk_index: int
    section_path: list[str] | None
    metadata: dict | None = None
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
        text: str,
        document_title: str,
        business_scene: str | None,
    ) -> ChunkBuildResult:
        """将清洗后的文本转换为父块和子块。"""
        pass
