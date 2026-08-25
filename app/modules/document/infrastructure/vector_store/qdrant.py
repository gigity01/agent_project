"""文档模块 Qdrant 向量存储客户端与集合管理适配器。

封装 Qdrant 客户端连接、Collection 自动初始化校验、向量点批量 upsert（Point ID 为整数 child_chunk_id）以及删除。
"""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from app.config.settings import (
    EMBEDDING_VECTOR_SIZE,
    QDRANT_COLLECTION_NAME,
    QDRANT_URL,
)


class QdrantVectorStore:
    """管理应用默认 Qdrant Collection 的连接、集合创建与向量批量读写。"""

    def __init__(self) -> None:
        """初始化 Qdrant 客户端并加载全局配置的 Collection 名称。"""
        self.client = QdrantClient(url=QDRANT_URL)
        self.collection_name = QDRANT_COLLECTION_NAME

    def ensure_collection(self) -> None:
        """仅当 Collection 不存在时，按配置的向量维度（EMBEDDING_VECTOR_SIZE）与余弦距离（COSINE）创建 Collection。"""
        if self.client.collection_exists(
            collection_name=self.collection_name
        ):
            return

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=EMBEDDING_VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )

    def upsert_points(self, points: list[PointStruct]) -> None:
        """同步批量写入向量点至 Qdrant Collection（wait=True 确保持久化）。

        Args:
            points: 包含 ID、向量数据与 Payload 的 PointStruct 列表。
        """
        if not points:
            return

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )

    def delete_points(self, point_ids: list[int]) -> None:
        """根据整数 Point ID（即 child_chunks.id）列表批量删除向量点。

        Args:
            point_ids: 待删除的 Point ID 整数列表。
        """
        if not point_ids:
            return

        self.client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=point_ids),
            wait=True,
        )
