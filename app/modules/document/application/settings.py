"""Document 用例所需的不可变运行参数。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocumentUploadSettings:
    raw_local_storage_dir: Path
    raw_external_storage_dir: Path
    max_upload_file_size: int
    default_document_status: str
    default_document_version: int
    default_created_by_actor_code: str
    document_code_prefix: str
    document_code_random_length: int


@dataclass(frozen=True)
class DocumentProcessingSettings:
    cleaned_storage_dir: Path
    secondary_text_storage_dir: Path
    staging_storage_dir: Path


@dataclass(frozen=True)
class DocumentIndexingSettings:
    embedding_batch_size: int
    embedding_model_name: str
    embedding_vector_size: int
