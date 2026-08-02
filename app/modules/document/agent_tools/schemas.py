"""Document Agent Tool 的显式输入输出 Schema。"""

from typing import Literal

from pydantic import BaseModel, Field

from app.modules.document.application.dto import (
    DocumentArtifactResult,
    DocumentListItem,
    DocumentPipelineStateResult,
    DocumentResult,
)


class GetDocumentToolInput(BaseModel):
    document_id: int = Field(..., gt=0)


class ListDocumentsToolInput(BaseModel):
    kb_id: int = Field(..., gt=0)
    status: str | None = None
    source_type: str | None = None
    lifecycle_status: str | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class GetDocumentPipelineStateToolInput(BaseModel):
    document_id: int = Field(..., gt=0)


class ListDocumentArtifactsToolInput(BaseModel):
    document_id: int = Field(..., gt=0)


class ProcessDocumentToolInput(BaseModel):
    document_id: int = Field(..., gt=0)


class BuildDocumentChunksToolInput(BaseModel):
    document_id: int = Field(..., gt=0)


class IndexDocumentVectorsToolInput(BaseModel):
    document_id: int = Field(..., gt=0)


class ToolResult(BaseModel):
    """所有 Tool 返回给模型的稳定调用语义。"""

    outcome: Literal["succeeded", "rejected", "failed"]
    result_code: str
    message: str
    retryable: bool
    resource_refs: list[str]


class DocumentToolView(DocumentResult):
    """Document Tool 使用的完整文档视图。"""


class DocumentListToolItem(DocumentListItem):
    """Document Tool 使用的列表项。"""


class DocumentPipelineToolView(DocumentPipelineStateResult):
    """Document Tool 使用的流水线状态快照。"""


class DocumentArtifactToolView(DocumentArtifactResult):
    """Document Tool 使用的派生产物视图。"""


class GetDocumentToolOutput(ToolResult):
    document: DocumentToolView | None = None


class ListDocumentsToolOutput(ToolResult):
    documents: list[DocumentListToolItem] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0


class GetDocumentPipelineStateToolOutput(ToolResult):
    pipeline_state: DocumentPipelineToolView | None = None


class ListDocumentArtifactsToolOutput(ToolResult):
    document_id: int
    source_uri: str | None = None
    source_type: str | None = None
    original_filename: str | None = None
    artifacts: list[DocumentArtifactToolView] = Field(default_factory=list)


class ProcessDocumentToolOutput(ToolResult):
    document_id: int
    document_status: str | None = None
    cleaned_uri: str | None = None


class BuildDocumentChunksToolOutput(ToolResult):
    document_id: int
    document_status: str | None = None
    parent_count: int | None = None
    child_count: int | None = None


class IndexDocumentVectorsToolOutput(ToolResult):
    document_id: int
    document_status: str | None = None
    total_chunks: int | None = None
    indexed_chunks: int | None = None
    failed_chunks: int | None = None
