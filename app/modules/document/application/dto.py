"""文档应用层命令与结果 DTO。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentResult(BaseModel):
    """上传或生命周期操作返回的完整文档视图。"""

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

    model_config = ConfigDict(from_attributes=True)


class ProcessDocumentResult(BaseModel):
    document_id: int
    doc_code: str
    source_type: str
    source_uri: str
    cleaned_uri: str
    status: str


class BuildChunksResult(BaseModel):
    document_id: int
    doc_code: str
    source_type: str
    parent_count: int
    child_count: int
    status: str


class IndexVectorsResult(BaseModel):
    document_id: int
    total_chunks: int
    indexed_chunks: int
    failed_chunks: int
    status: str


class DocumentArtifactCreate(BaseModel):
    """创建文档派生产物所需的持久化字段。"""

    document_id: int
    artifact_code: str
    artifact_type: str
    artifact_role: str
    artifact_format: str
    artifact_uri: str
    artifact_hash: str | None = None
    hash_algorithm: str | None = "sha256"
    provider: str | None = None
    processor: str | None = None
    file_size: int | None = None
    char_count: int | None = None
    line_count: int | None = None
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by_actor_code: str | None = None
