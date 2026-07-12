"""文档向量索引接口的响应模型。"""

from pydantic import BaseModel

class VectorIndexingResponse(BaseModel):
    """一次向量索引任务的处理数量和最终状态。"""
    document_id: int
    total_chunks: int
    indexed_chunks: int
    failed_chunks: int
    status: str
