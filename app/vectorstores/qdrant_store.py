"""Qdrant collection 初始化与向量点写入封装。"""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from app.app_config.settings import (
    QDRANT_URL,
    QDRANT_COLLECTION_NAME,
    EMBEDDING_VECTOR_SIZE,
)


class QdrantVectorStore:
    """管理应用默认 Qdrant collection 的连接和 upsert 操作。"""
    def __init__(self) -> None:
        """创建 Qdrant 客户端并加载默认 collection 名称。"""
        self.client = QdrantClient(url=QDRANT_URL)
        self.collection_name = QDRANT_COLLECTION_NAME

    def ensure_collection(self) -> None:
        """仅在 collection 不存在时按当前向量维度创建它。

        该方法不会修改已有 collection 的 schema；维度或距离度量变更必须通过
        专门的迁移/重建流程处理，避免破坏已索引向量。
        """
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
        """同步写入一批向量点；调用方须先确保 collection 存在。"""
        if not points:
            return

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )

    def delete_points(self, point_ids: list[int]) -> None:
        """按稳定 Point ID 尽力删除一批已写入向量。"""
        if not point_ids:
            return

        self.client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=point_ids),
            wait=True,
        )
