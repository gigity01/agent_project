"""文档模块的 HTTP 请求与响应 Schema。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.document.application.dto import (
    BuildChunksResult,
    ChildChunkSearchQuery,
    DocumentArtifactSearchQuery,
    DocumentChunkStatisticsResult,
    DocumentPipelineStateResult,
    DocumentResult,
    DocumentSearchQuery,
    IndexVectorsResult,
    KnowledgeBaseStatisticsResult,
    ListChildChunksResult,
    ListDocumentArtifactsResult,
    ListParentBlocksResult,
    ParentBlockSearchQuery,
    ProcessDocumentResult,
    SearchDocumentArtifactsResult,
    SearchDocumentsResult,
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


class DocumentSearchRequest(DocumentSearchQuery):
    """文档高级查询 HTTP 请求。"""


class DocumentSearchResponse(SearchDocumentsResult):
    """文档高级查询 HTTP 响应。"""


class DocumentPipelineStateResponse(DocumentPipelineStateResult):
    """文档流水线状态 HTTP 响应。"""


class DocumentArtifactsResponse(ListDocumentArtifactsResult):
    """单文档派生产物 HTTP 响应。"""


class DocumentArtifactSearchRequest(DocumentArtifactSearchQuery):
    """派生产物高级查询 HTTP 请求。"""


class DocumentArtifactSearchResponse(SearchDocumentArtifactsResult):
    """派生产物高级查询 HTTP 响应。"""


class ParentBlockSearchRequest(ParentBlockSearchQuery):
    """父级语义块查询 HTTP 请求。"""


class ParentBlockSearchResponse(ListParentBlocksResult):
    """父级语义块查询 HTTP 响应。"""


class ChildChunkSearchRequest(ChildChunkSearchQuery):
    """子块查询 HTTP 请求。"""


class ChildChunkSearchResponse(ListChildChunksResult):
    """子块查询 HTTP 响应。"""


class DocumentChunkStatisticsResponse(DocumentChunkStatisticsResult):
    """文档切块统计 HTTP 响应。"""


class KnowledgeBaseStatisticsResponse(KnowledgeBaseStatisticsResult):
    """知识库统计 HTTP 响应。"""
