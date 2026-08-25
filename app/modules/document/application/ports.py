"""Document Application 端口（Ports）接口定义。

定义文档应用层用例与外部基础设施解耦所需的 Protocol 契约及统一依赖注入容器。
符合依赖倒置原则（DIP），具体实现在 Infrastructure 层提供并由 Bootstrap 装配。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, ContextManager, Protocol


class UploadFilePort(Protocol):
    """文件上传抽象协议。

    解耦 FastAPI UploadFile 或其他来源的文件流。

    Attributes:
        filename: 客户端上传时声明的原始文件名。
        content_type: 客户端声明的 MIME 类型（如 'application/pdf', 'text/plain' 等）。
    """

    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes:
        """异步分块读取上传文件的原始字节。

        Args:
            size: 本次期望读取的最大字节数；-1 表示读取全部剩余字节。

        Returns:
            读取到的字节流。
        """
        ...


class UploadMetadataPort(Protocol):
    """文档上传时附带的表单元数据抽象协议。

    Attributes:
        title: 文档用户可见标题。
        kb_id: 归属知识库 ID。
        domain_code: 业务领域编码。
        business_scene: 业务场景标识。
        risk_level: 风险等级（如 'low', 'medium', 'high'）。
        effective_at: 业务生效时间。
        expired_at: 业务失效时间。
    """

    title: str
    kb_id: int
    domain_code: str
    business_scene: str | None
    risk_level: str
    effective_at: Any
    expired_at: Any


class ExternalEffectFencePort(Protocol):
    """外部副作用互斥围栏端口协议。

    使用 MySQL 命名锁（GET_LOCK/RELEASE_LOCK）或分布式锁在跨进程/Worker 间
    串行化对同一文档外部资源（如文件目录操作、Qdrant 向量写入与清理）的副作用，
    防止并发 Attempt 或并发补偿产生数据竞争与脏写。
    """

    def hold(self, resource_key: str) -> ContextManager[None]:
        """获取并保持针对指定资源键的排他围栏锁上下文。

        Args:
            resource_key: 资源锁唯一键（如 'document:process:123', 'document:index:123'）。

        Returns:
            上下文管理器；退出上下文时自动释放锁。
        """
        ...


@dataclass(frozen=True)
class DocumentApplicationPorts:
    """由 Bootstrap 装配并显式注入 Document 业务用例的外部能力与工厂端口容器。

    Attributes:
        uow_factory: 数据库工作单元（Unit of Work）工厂函数。
        document_factory: Document 领域/持久化模型构造工厂。
        parent_block_factory: ParentBlock 领域/持久化模型构造工厂。
        child_chunk_factory: ChildChunk 领域/持久化模型构造工厂。
        processor_factory: 依据源格式创建文本清洗 Processor 的工厂。
        chunker_factory: 依据源格式创建分块 Chunker 的工厂。
        embedding_factory: DashScope / OpenAI Embedding 客户端工厂。
        vector_store_factory: Qdrant 向量存储操作客户端工厂。
        external_effect_fence: 外部副作用命名锁互斥围栏端口实例。
        docling_factory: Docling 外部格式转换服务客户端工厂。
        point_factory: Qdrant PointStruct 向量点构造工厂。
        validate_content_type: 校验上传文件 MIME 类型的函数。
        get_safe_extension: 安全提取并校验文件扩展名的函数。
        calculate_file_hash: 计算文件 SHA-256 哈希的工具函数。
        cleanup_file: 物理清理落盘文件的工具函数。
        integrity_error_type: 数据库唯一性约束冲突异常类型（用于查重捕获）。
    """

    uow_factory: Callable[[], Any]
    document_factory: Callable[..., Any]
    parent_block_factory: Callable[..., Any]
    child_chunk_factory: Callable[..., Any]
    processor_factory: Callable[[str], Any]
    chunker_factory: Callable[[str], Any]
    embedding_factory: Callable[[], Any]
    vector_store_factory: Callable[[], Any]
    external_effect_fence: ExternalEffectFencePort
    docling_factory: Callable[[], Any]
    point_factory: Callable[..., Any]
    validate_content_type: Callable[[UploadFilePort], None]
    get_safe_extension: Callable[[str], str]
    calculate_file_hash: Callable[[Path], str]
    cleanup_file: Callable[[Path], bool]
    integrity_error_type: type[BaseException]

    def is_integrity_error(self, exc: BaseException) -> bool:
        """判定给定异常是否属于数据库完整性约束冲突异常（如 SHA-256 重复）。

        Args:
            exc: 捕获的底层异常对象。

        Returns:
            若为唯一键冲突等完整性异常返回 True，否则返回 False。
        """
        return isinstance(exc, self.integrity_error_type)
