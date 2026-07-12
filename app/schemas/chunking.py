"""文档切块接口的响应模型。"""

from pydantic import BaseModel


class BuildChunksResponse(BaseModel):
    """一次切块任务的结果统计。"""
    document_id: int
    doc_code: str
    source_type: str
    parent_count: int
    child_count: int
    status: str
