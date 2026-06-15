from abc import ABC, abstractmethod
from dataclasses import dataclass



@dataclass
class ParentBlockData:
    block_type: str
    title: str | None
    section_path: list[str] | None
    content: str
    block_index: int
    metadata: dict | None = None

@dataclass
class ChildChunkData:
    content: str
    embedding_text: str
    chunk_index: int
    section_path: list[str] | None
    metadata: dict | None = None
    chunk_type: str = "text"


@dataclass
class ChunkBuildResult:
    parents: list[ParentBlockData]
    children_by_parent_index: dict[int, list[ChildChunkData]]


class BaseChunker(ABC):
    @abstractmethod
    def build(
        self,
        text: str,
        document_title: str,
        business_scene: str | None,
    ) -> ChunkBuildResult:
        pass