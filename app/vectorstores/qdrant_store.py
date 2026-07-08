# app/vectorstores/qdrant_store.py

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from app.app_config.settings import (
    QDRANT_URL,
    QDRANT_COLLECTION_NAME,
    EMBEDDING_VECTOR_SIZE,
)


class QdrantVectorStore:
    def __init__(self) -> None:
        self.client = QdrantClient(url=QDRANT_URL)
        self.collection_name = QDRANT_COLLECTION_NAME

    def ensure_collection(self) -> None:
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
        if not points:
            return

        self.ensure_collection()

        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
            wait=True,
        )