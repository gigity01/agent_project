from openai import OpenAI

from app.app_config.settings import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_BATCH_SIZE,
)

class EmbeddingService:
    """
      Qwen / DashScope embedding service.

      输入:
          list[str]

      输出:
          list[list[float]]
      """

    def __init__(self) -> None:
        if not DASHSCOPE_API_KEY:
            raise RuntimeError("DASHSCOPE_API_KEY 未配置")

        self.client = OpenAI(
            api_key=DASHSCOPE_API_KEY,
            base_url=DASHSCOPE_BASE_URL,
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
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
        return [
            texts[i:i + EMBEDDING_BATCH_SIZE]
            for i in range(0, len(texts), EMBEDDING_BATCH_SIZE)
        ]