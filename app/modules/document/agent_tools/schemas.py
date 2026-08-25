"""Document Agent Function Tool 的显式输入输出 Schema 与结果视图定义。

为 OpenAI Agents SDK / Agent Tool 调用提供显式参数校验与格式化输出封装。
所有 ToolOutput 均继承统一的 ToolResult 协议（包含 outcome, result_code, retryable, resource_refs 等）。
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.modules.document.application.dto import (
    ChildChunkResult,
    ChildChunkSearchQuery,
    DocumentArtifactResult,
    DocumentArtifactSearchQuery,
    DocumentChunkStatisticsResult,
    DocumentListItem,
    DocumentSearchQuery,
    DocumentPipelineStateResult,
    DocumentResult,
    KnowledgeBaseStatisticsResult,
    ParentBlockResult,
    ParentBlockSearchQuery,
)


class GetDocumentToolInput(BaseModel):
    """获取单份文档详情 Tool 的输入参数。"""

    document_id: int = Field(..., gt=0, description="文档 ID")


class ListDocumentsToolInput(BaseModel):
    """基础筛选文档列表 Tool 的输入参数。"""

    kb_id: int = Field(..., gt=0, description="所属知识库 ID")
    status: str | None = Field(default=None, description="流水线技术状态")
    source_type: str | None = Field(default=None, description="原始文件格式")
    lifecycle_status: str | None = Field(default=None, description="业务生命周期状态")
    limit: int = Field(default=50, ge=1, le=100, description="返回条数限制")
    offset: int = Field(default=0, ge=0, description="偏移量")


class SearchDocumentsToolInput(DocumentSearchQuery):
    """文档多条件高级检索 Tool 的输入参数。"""


class GetDocumentPipelineStateToolInput(BaseModel):
    """获取文档流水线状态 Tool 的输入参数。"""

    document_id: int = Field(..., gt=0, description="文档 ID")


class ListDocumentArtifactsToolInput(BaseModel):
    """列出文档派生产物 Tool 的输入参数。"""

    document_id: int = Field(..., gt=0, description="文档 ID")


class SearchDocumentArtifactsToolInput(DocumentArtifactSearchQuery):
    """派生产物高级检索 Tool 的输入参数。"""


class ListParentBlocksToolInput(ParentBlockSearchQuery):
    """父级语义块检索 Tool 的输入参数。"""


class ListChildChunksToolInput(ChildChunkSearchQuery):
    """可向量化子块检索 Tool 的输入参数。"""


class GetDocumentChunkStatisticsToolInput(BaseModel):
    """获取文档切块统计 Tool 的输入参数。"""

    document_id: int = Field(..., gt=0, description="文档 ID")


class GetKnowledgeBaseStatisticsToolInput(BaseModel):
    """获取知识库宏观统计 Tool 的输入参数。"""

    kb_id: int = Field(..., gt=0, description="知识库 ID")


class ProcessDocumentToolInput(BaseModel):
    """执行文档清洗与格式转换命令 Tool 的输入参数。"""

    document_id: int = Field(..., gt=0, description="待处理文档 ID")


class BuildDocumentChunksToolInput(BaseModel):
    """执行文档父子切块构建命令 Tool 的输入参数。"""

    document_id: int = Field(..., gt=0, description="待切块文档 ID")


class IndexDocumentVectorsToolInput(BaseModel):
    """执行文档向量生成与写入命令 Tool 的输入参数。"""

    document_id: int = Field(..., gt=0, description="待索引文档 ID")


class ToolResult(BaseModel):
    """所有 Agent Tool 统一返回的标准化执行结果基类。

    Attributes:
        outcome: 执行最终结果类别（'succeeded', 'rejected', 'failed'）。
        result_code: 机器可读的结构化结果编码（如 'document_retrieved', 'document_processed'）。
        message: 人类可读的执行结果摘要信息。
        retryable: 失败时是否建议重试。
        resource_refs: 本次调用涉及的领域资源引用列表（如 ['document:123']）。
    """

    outcome: Literal["succeeded", "rejected", "failed"]
    result_code: str
    message: str
    retryable: bool
    resource_refs: list[str]


class DocumentToolView(DocumentResult):
    """Document Tool 返回的完整文档实体详情视图。"""


class DocumentListToolItem(DocumentListItem):
    """Document Tool 列表查询返回的单条文档摘要项。"""


class DocumentPipelineToolView(DocumentPipelineStateResult):
    """Document Tool 返回的流水线三状态轴与进度快照视图。"""


class DocumentArtifactToolView(DocumentArtifactResult):
    """Document Tool 返回的派生产物详情视图。"""


class ParentBlockToolView(ParentBlockResult):
    """Document Tool 返回的父级语义块实体视图。"""


class ChildChunkToolView(ChildChunkResult):
    """Document Tool 返回的可向量化子块实体视图。"""


class DocumentChunkStatisticsToolView(DocumentChunkStatisticsResult):
    """Document Tool 返回的切块与向量状态统计视图。"""


class KnowledgeBaseStatisticsToolView(KnowledgeBaseStatisticsResult):
    """Document Tool 返回的知识库统计视图。"""


class GetDocumentToolOutput(ToolResult):
    """获取单份文档详情 Tool 的返回输出。"""

    document: DocumentToolView | None = None


class ListDocumentsToolOutput(ToolResult):
    """文档基础列表查询 Tool 的返回输出。"""

    documents: list[DocumentListToolItem] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0


class SearchDocumentsToolOutput(ListDocumentsToolOutput):
    """文档多条件高级检索 Tool 的返回输出。"""


class GetDocumentPipelineStateToolOutput(ToolResult):
    """获取文档流水线状态 Tool 的返回输出。"""

    pipeline_state: DocumentPipelineToolView | None = None


class ListDocumentArtifactsToolOutput(ToolResult):
    """列出文档派生产物 Tool 的返回输出。"""

    document_id: int
    source_uri: str | None = None
    source_type: str | None = None
    original_filename: str | None = None
    artifacts: list[DocumentArtifactToolView] = Field(default_factory=list)


class SearchDocumentArtifactsToolOutput(ToolResult):
    """派生产物高级检索 Tool 的返回输出。"""

    artifacts: list[DocumentArtifactToolView] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0


class ListParentBlocksToolOutput(ToolResult):
    """父级语义块检索 Tool 的返回输出。"""

    parent_blocks: list[ParentBlockToolView] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0


class ListChildChunksToolOutput(ToolResult):
    """可向量化子块检索 Tool 的返回输出。"""

    child_chunks: list[ChildChunkToolView] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0


class GetDocumentChunkStatisticsToolOutput(ToolResult):
    """获取文档切块统计 Tool 的返回输出。"""

    statistics: DocumentChunkStatisticsToolView | None = None


class GetKnowledgeBaseStatisticsToolOutput(ToolResult):
    """获取知识库统计 Tool 的返回输出。"""

    statistics: KnowledgeBaseStatisticsToolView | None = None


class ProcessDocumentToolOutput(ToolResult):
    """执行文档清洗转换命令 Tool 的返回输出。"""

    document_id: int
    document_status: str | None = None
    cleaned_uri: str | None = None


class BuildDocumentChunksToolOutput(ToolResult):
    """执行文档切块构建命令 Tool 的返回输出。"""

    document_id: int
    document_status: str | None = None
    parent_count: int | None = None
    child_count: int | None = None


class IndexDocumentVectorsToolOutput(ToolResult):
    """执行文档向量索引命令 Tool 的返回输出。"""

    document_id: int
    document_status: str | None = None
    total_chunks: int | None = None
    indexed_chunks: int | None = None
    failed_chunks: int | None = None
