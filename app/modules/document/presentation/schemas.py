"""文档模块的 HTTP 请求与响应 Schema。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.document.application.dto import (
    BuildChunksResult,
    DocumentResult,
    IndexVectorsResult,
    ProcessDocumentResult,
)


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


class DocumentResponse(DocumentResult):
    """上传成功后返回的完整文档视图。"""

    pass


class DocumentProcessResponse(ProcessDocumentResult):
    """文档清洗或转换完成后的状态视图。"""

    pass


class BuildChunksResponse(BuildChunksResult):
    """一次切块任务的结果统计。"""

    pass


class VectorIndexingResponse(IndexVectorsResult):
    """一次向量索引任务的处理数量和最终状态。"""

    pass
