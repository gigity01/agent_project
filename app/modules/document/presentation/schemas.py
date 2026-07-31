"""文档模块的 HTTP 请求与响应 Schema。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "critical"]


class DocumentUploadFormData(BaseModel):
    """上传接口从 multipart 表单解析出的文档业务元数据。"""

    title: str = Field(..., min_length=1, max_length=255)
    kb_id: int = Field(..., gt=0)
    domain_code: str = Field(..., min_length=1, max_length=255)
    business_scene: str | None = Field(min_length=1, max_length=255)
    risk_level: RiskLevel = "low"
    effective_at: datetime | None = None
    expired_at: datetime | None = None


class DocumentResponse(BaseModel):
    """上传成功后返回的完整文档视图。"""

    id: int
    doc_code: str
    kb_id: int
    domain_code: str
    business_scene: str | None
    title: str
    original_filename: str | None
    file_size: int | None
    source_type: str
    source_uri: str
    cleaned_uri: str | None
    content_hash: str
    active_content_hash: str | None
    lifecycle_status: str
    storage_status: str
    version: int
    status: str
    replaced_by: int | None
    risk_level: str | None
    effective_at: datetime | None
    expired_at: datetime | None
    created_by_actor_code: str | None
    created_at: datetime
    updated_at: datetime
    indexed_at: datetime | None

    model_config = {"from_attributes": True}


class DocumentProcessResponse(BaseModel):
    """文档清洗或转换完成后的状态视图。"""

    document_id: int
    doc_code: str
    source_type: str
    source_uri: str
    cleaned_uri: str
    status: str


class BuildChunksResponse(BaseModel):
    """一次切块任务的结果统计。"""

    document_id: int
    doc_code: str
    source_type: str
    parent_count: int
    child_count: int
    status: str


class VectorIndexingResponse(BaseModel):
    """一次向量索引任务的处理数量和最终状态。"""

    document_id: int
    total_chunks: int
    indexed_chunks: int
    failed_chunks: int
    status: str
