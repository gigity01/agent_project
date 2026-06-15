from pydantic import BaseModel


class BuildChunksResponse(BaseModel):
    document_id: int
    doc_code: str
    source_type: str
    parent_count: int
    child_count: int
    status: str