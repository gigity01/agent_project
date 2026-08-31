"""文档模块切块策略抽象基类与数据协议定义。"""

from abc import ABC, abstractmethod

from app.modules.document.domain.models import (
    ChildChunkData,
    ChunkBuildInput,
    ChunkBuildResult,
    ParentBlockData,
)


class BaseChunker(ABC):
    """不同源文本格式切块策略的抽象基类。"""

    @abstractmethod
    def build(
        self,
        input_data: ChunkBuildInput,
    ) -> ChunkBuildResult:
        """读取已清洗文件并转换为分层的父级语义块与子切块集合。

        Args:
            input_data: 包含 cleaned_path 与 process_metadata 的切块输入数据对象。

        Returns:
            ChunkBuildResult: 包含 parent 列表和按 parent_index 组织的 child 列表的结果对象。

        Raises:
            ValueError: 文本格式不合法、超长或缺少必要元数据时抛出。
        """
        raise NotImplementedError
