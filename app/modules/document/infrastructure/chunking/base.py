"""文档模块切块器的输入、输出数据结构和统一接口。"""

from abc import ABC, abstractmethod

from app.modules.document.domain.models import (
    ChildChunkData,
    ChunkBuildInput,
    ChunkBuildResult,
    ParentBlockData,
)


class BaseChunker(ABC):
    """不同源文本格式的切块策略抽象基类。"""
    @abstractmethod
    def build(
        self,
        input_data: ChunkBuildInput,
    ) -> ChunkBuildResult:
        """读取 cleaned 文件并转换为父块和子块。"""
        raise NotImplementedError
