from pydantic import BaseModel

class VectorIndexingResponse(BaseModel):
    document_id: int
    total_chunks: int
    indexed_chunks: int
    failed_chunks: int
    status: str