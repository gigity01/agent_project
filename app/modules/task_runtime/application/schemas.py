"""每个确定性文档 Capability 的独立输入/输出 Schema 定义。

提供以下三种文档能力的数据契约模型：
1. ProcessDocumentTaskPayload / ProcessDocumentTaskOutput: 文档清洗处理。
2. BuildDocumentChunksTaskPayload / BuildDocumentChunksTaskOutput: 父子分块。
3. IndexDocumentVectorsTaskPayload / IndexDocumentVectorsTaskOutput: 向量索引。
"""

from pydantic import BaseModel, ConfigDict, Field


class _Payload(BaseModel):
    """所有 Task Payload 的基类，禁止未声明字段。"""

    model_config = ConfigDict(extra="forbid")


class ProcessDocumentTaskPayload(_Payload):
    """文档处理（Process Document）任务的输入负载。"""

    document_id: int = Field(gt=0, description="待处理文档的全局唯一数字 ID")


class BuildDocumentChunksTaskPayload(_Payload):
    """文档切块（Build Document Chunks）任务的输入负载。"""

    document_id: int = Field(gt=0, description="待切块文档的全局唯一数字 ID")


class IndexDocumentVectorsTaskPayload(_Payload):
    """文档向量索引（Index Document Vectors）任务的输入负载。"""

    document_id: int = Field(gt=0, description="待索引文档的全局唯一数字 ID")


class ProcessDocumentTaskOutput(BaseModel):
    """文档处理任务的成功输出结果。"""

    document_id: int = Field(description="文档 ID")
    status: str = Field(description="处理后的文档状态（如 processed）")
    cleaned_uri: str = Field(description="清洗后规范化文本文件的存储 URI")


class BuildDocumentChunksTaskOutput(BaseModel):
    """文档切块任务的成功输出结果。"""

    document_id: int = Field(description="文档 ID")
    status: str = Field(description="切块后的文档状态（如 chunked）")
    parent_count: int = Field(description="生成的父级语义块（parent blocks）数量")
    child_count: int = Field(description="生成的可向量化子块（child chunks）数量")


class IndexDocumentVectorsTaskOutput(BaseModel):
    """文档向量索引任务的成功输出结果。"""

    document_id: int = Field(description="文档 ID")
    status: str = Field(description="索引后的文档状态（如 indexed）")
    indexed_chunks: int = Field(description="本次成功生成向量并写入 Qdrant 的子块数量")
    failed_chunks: int = Field(description="索引失败的子块数量")
