"""文档上传与处理接口使用的 Pydantic 请求、响应模型。"""

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

    model_config = {
        "from_attributes": True
    }


class DocumentProcessResponse(BaseModel):
    """文档清洗或转换完成后的状态视图。"""
    document_id: int
    doc_code: str
    source_type: str
    source_uri: str
    cleaned_uri: str
    status: str
