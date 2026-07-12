"""通过 DashScope OpenAI 兼容接口批量生成文本向量。"""

from openai import OpenAI

from app.app_config.settings import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_BATCH_SIZE,
)

class EmbeddingService:
    """封装 Qwen / DashScope embedding 服务的客户端和批量调用。"""

    def __init__(self) -> None:
        """校验配置并创建 OpenAI 兼容客户端。"""
        if not DASHSCOPE_API_KEY:
            raise RuntimeError("DASHSCOPE_API_KEY 未配置")

        self.client = OpenAI(
            api_key=DASHSCOPE_API_KEY,
            base_url=DASHSCOPE_BASE_URL,
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """按服务端批量限制为文本列表生成向量。"""
        if not texts:
            return []

        all_vectors: list[list[float]] = []
        for batch in self._batch_texts(texts):
            response = self.client.embeddings.create(
                model=EMBEDDING_MODEL_NAME,
                input=batch,
            )

            vectors = [item.embedding for item in response.data]
            all_vectors.extend(vectors)
        return all_vectors

    def _batch_texts(self, texts: list[str]) -> list[list[str]]:
        """按配置的最大批量大小分组文本。"""
        return [
            texts[i:i + EMBEDDING_BATCH_SIZE]
            for i in range(0, len(texts), EMBEDDING_BATCH_SIZE)
        ]
