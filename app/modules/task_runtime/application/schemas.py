"""每个确定性文档 Capability 的独立输入/输出 Schema。"""

from pydantic import BaseModel, ConfigDict, Field


class _Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProcessDocumentTaskPayload(_Payload):
    document_id: int = Field(gt=0)


class BuildDocumentChunksTaskPayload(_Payload):
    document_id: int = Field(gt=0)


class IndexDocumentVectorsTaskPayload(_Payload):
    document_id: int = Field(gt=0)


class ProcessDocumentTaskOutput(BaseModel):
    document_id: int
    status: str
    cleaned_uri: str


class BuildDocumentChunksTaskOutput(BaseModel):
    document_id: int
    status: str
    parent_count: int
    child_count: int


class IndexDocumentVectorsTaskOutput(BaseModel):
    document_id: int
    status: str
    indexed_chunks: int
    failed_chunks: int
