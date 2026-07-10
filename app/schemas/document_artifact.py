from datetime import datetime

from pydantic import Field,ConfigDict,BaseModel
from typing import Any

class DocumentArtifactCreate(BaseModel):

    document_id : int
    artifact_code: str

    artifact_type: str
    artifact_role: str
    artifact_format: str

    artifact_uri: str

    artifact_hash: str | None = None
    hash_algorithm: str | None = "sha256"

    provider : str | None = None
    processor : str | None = None

    file_size: int | None = None
    char_count: int | None = None
    line_count: int | None = None

    status: str  = "active"

    metadata: dict[str,Any] = Field(default_factory=dict)

    created_by_actor_code :str | None = None


class ArtifactResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    document_id: int
    artifact_code: str

    artifact_type: str
    artifact_role: str
    artifact_format: str

    artifact_uri: str
    artifact_hash: str | None
    hash_algorithm: str | None

    provider : str | None
    processor : str | None

    file_size: str | None
    char_count: str | None
    line_count: str | None
    status: str | None


    metadata_json: dict[str,Any] | None

    create_by_actor_code : str | None = None

    create_at: datetime
    update_at: datetime

