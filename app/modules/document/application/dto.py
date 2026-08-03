"""文档应用层命令与结果 DTO。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, model_validator


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


class DocumentListQuery(BaseModel):
    """文档列表查询条件。"""

    kb_id: int = Field(..., gt=0)
    status: str | None = None
    source_type: str | None = None
    lifecycle_status: str | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class DocumentListItem(BaseModel):
    """列表场景所需的稳定文档摘要。"""

    id: int
    doc_code: str
    kb_id: int
    title: str
    source_type: str
    lifecycle_status: str
    storage_status: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    indexed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ListDocumentsResult(BaseModel):
    """带总数和稳定分页信息的文档列表。"""

    items: list[DocumentListItem]
    total: int
    limit: int
    offset: int


class DocumentSearchQuery(BaseModel):
    """Agent 可控字段受限的文档高级查询条件。"""

    kb_ids: list[PositiveInt] = Field(default_factory=list)
    document_ids: list[PositiveInt] = Field(default_factory=list)
    doc_codes: list[str] = Field(default_factory=list)
    domain_codes: list[str] = Field(default_factory=list)
    business_scenes: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    lifecycle_statuses: list[str] = Field(default_factory=list)
    storage_statuses: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    risk_levels: list[str] = Field(default_factory=list)
    keyword: str | None = None
    original_filename: str | None = None
    created_by_actor_code: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    updated_from: datetime | None = None
    updated_to: datetime | None = None
    indexed_from: datetime | None = None
    indexed_to: datetime | None = None
    effective_at_before: datetime | None = None
    expired_at_before: datetime | None = None
    has_cleaned_output: bool | None = None
    has_active_content_hash: bool | None = None
    replaced_by: int | None = Field(default=None, gt=0)
    sort_by: Literal[
        "id",
        "created_at",
        "updated_at",
        "indexed_at",
        "title",
    ] = "id"
    sort_order: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_time_ranges(self) -> "DocumentSearchQuery":
        for start_name, end_name in (
            ("created_from", "created_to"),
            ("updated_from", "updated_to"),
            ("indexed_from", "indexed_to"),
        ):
            start = getattr(self, start_name)
            end = getattr(self, end_name)
            if start is not None and end is not None and start > end:
                raise ValueError(f"{start_name} 不能晚于 {end_name}")
        return self


class SearchDocumentsResult(ListDocumentsResult):
    """文档高级查询的稳定分页结果。"""


class DocumentPipelineStateResult(BaseModel):
    """文档三状态轴及切块、向量进度的只读快照。"""

    document_id: int
    doc_code: str
    source_type: str
    source_uri: str
    cleaned_uri: str | None
    document_status: str
    lifecycle_status: str
    storage_status: str
    parent_count: int
    child_count: int
    vector_status_counts: dict[str, int]
    indexed_at: datetime | None


class DocumentArtifactResult(BaseModel):
    """Agent 可读取的文档产物元数据。"""

    id: int
    document_id: int
    artifact_code: str
    artifact_type: str
    artifact_role: str
    artifact_format: str
    artifact_uri: str
    artifact_hash: str | None
    hash_algorithm: str | None
    provider: str | None
    processor: str | None
    file_size: int | None
    char_count: int | None
    line_count: int | None
    status: str
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="metadata_json",
    )
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ListDocumentArtifactsResult(BaseModel):
    """指定文档的全部派生产物。"""

    document_id: int
    source_uri: str
    source_type: str
    original_filename: str | None
    items: list[DocumentArtifactResult]


class DocumentArtifactSearchQuery(BaseModel):
    """派生产物多条件查询。"""

    document_ids: list[PositiveInt] = Field(default_factory=list)
    artifact_types: list[str] = Field(default_factory=list)
    artifact_roles: list[str] = Field(default_factory=list)
    artifact_formats: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    providers: list[str] = Field(default_factory=list)
    processors: list[str] = Field(default_factory=list)
    created_from: datetime | None = None
    created_to: datetime | None = None
    active_only: bool | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_created_range(self) -> "DocumentArtifactSearchQuery":
        if (
            self.created_from is not None
            and self.created_to is not None
            and self.created_from > self.created_to
        ):
            raise ValueError("created_from 不能晚于 created_to")
        return self


class SearchDocumentArtifactsResult(BaseModel):
    items: list[DocumentArtifactResult]
    total: int
    limit: int
    offset: int


class ParentBlockSearchQuery(BaseModel):
    """父级语义块受限字段查询。"""

    document_ids: list[PositiveInt] = Field(default_factory=list)
    parent_ids: list[PositiveInt] = Field(default_factory=list)
    kb_ids: list[PositiveInt] = Field(default_factory=list)
    block_types: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    section_path_contains: str | None = None
    keyword: str | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ParentBlockResult(BaseModel):
    id: int
    parent_code: str
    kb_id: int
    doc_id: int
    domain_code: str
    business_scene: str | None
    block_type: str
    title: str | None
    section_path: list[str] | None
    content: str
    content_hash: str | None
    block_index: int
    semantic_group_index: int
    segment_index: int
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ListParentBlocksResult(BaseModel):
    items: list[ParentBlockResult]
    total: int
    limit: int
    offset: int


class ChildChunkSearchQuery(BaseModel):
    """可向量化子块受限字段查询。"""

    document_id: int | None = Field(default=None, gt=0)
    parent_id: int | None = Field(default=None, gt=0)
    kb_id: int | None = Field(default=None, gt=0)
    vector_statuses: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    section_path_contains: str | None = None
    source_row_from: int | None = Field(default=None, ge=0)
    source_row_to: int | None = Field(default=None, ge=0)
    has_vector_id: bool | None = None
    keyword: str | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_source_row_range(self) -> "ChildChunkSearchQuery":
        if (
            self.source_row_from is not None
            and self.source_row_to is not None
            and self.source_row_from > self.source_row_to
        ):
            raise ValueError("source_row_from 不能大于 source_row_to")
        return self


class ChildChunkResult(BaseModel):
    id: int
    chunk_code: str
    parent_id: int
    doc_id: int
    kb_id: int
    domain_code: str
    business_scene: str | None
    chunk_index: int
    chunk_type: str
    section_path: list[str] | None
    source_row_index: int | None
    content: str
    embedding_text: str
    token_count: int | None
    vector_status: str
    qdrant_point_id: str | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    indexed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class ListChildChunksResult(BaseModel):
    items: list[ChildChunkResult]
    total: int
    limit: int
    offset: int


class DocumentChunkStatisticsResult(BaseModel):
    document_id: int
    doc_code: str
    parent_count: int
    child_count: int
    parent_status_counts: dict[str, int]
    child_status_counts: dict[str, int]
    vector_status_counts: dict[str, int]
    chunk_type_counts: dict[str, int]
    chunks_with_vector_id: int
    chunks_without_vector_id: int


class KnowledgeBaseStatisticsResult(BaseModel):
    kb_id: int
    kb_code: str
    name: str
    domain_code: str
    business_scene: str | None
    status: str
    visibility: str
    document_count: int
    active_document_count: int
    failed_document_count: int
    indexed_document_count: int
    parent_count: int
    child_count: int
    vector_status_counts: dict[str, int]


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
