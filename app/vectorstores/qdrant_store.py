"""Qdrant collection 初始化与向量点写入封装。"""

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

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
        """仅在 collection 不存在时按当前向量维度创建它。"""
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
        """确保 collection 存在后同步写入一批向量点。"""
        if not points:
            return

        self.ensure_collection()

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )
