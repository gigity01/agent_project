from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high", "critical"]


class DocumentUploadFormData(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    kb_id: int = Field(..., gt=0)
    domain_code: str = Field(..., min_length=1, max_length=255)
    business_scene: str | None = Field(min_length=1, max_length=255)
    risk_level: RiskLevel = "low"
    effective_at: datetime | None = None
    expired_at: datetime | None = None


class DocumentResponse(BaseModel):
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

    model_config = {
        "from_attributes": True
    }


class DocumentProcessResponse(BaseModel):
    document_id: int
    doc_code: str
    source_type: str
    source_uri: str
    cleaned_uri: str
    status: str
