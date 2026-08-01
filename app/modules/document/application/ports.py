"""Document Application 使用的外部能力 Port。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol


class UploadFilePort(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes:
        ...


class UploadMetadataPort(Protocol):
    title: str
    kb_id: int
    domain_code: str
    business_scene: str | None
    risk_level: str
    effective_at: Any
    expired_at: Any


@dataclass(frozen=True)
class DocumentApplicationPorts:
    """由 Bootstrap 显式注入 Document 用例的外部能力集合。"""

    uow_factory: Callable[[], Any]
    document_factory: Callable[..., Any]
    parent_block_factory: Callable[..., Any]
    child_chunk_factory: Callable[..., Any]
    processor_factory: Callable[[str], Any]
    chunker_factory: Callable[[str], Any]
    embedding_factory: Callable[[], Any]
    vector_store_factory: Callable[[], Any]
    docling_factory: Callable[[], Any]
    point_factory: Callable[..., Any]
    validate_content_type: Callable[[UploadFilePort], None]
    get_safe_extension: Callable[[str], str]
    calculate_file_hash: Callable[[Path], str]
    cleanup_file: Callable[[Path], bool]
    integrity_error_type: type[BaseException]

    def is_integrity_error(self, exc: BaseException) -> bool:
        return isinstance(exc, self.integrity_error_type)
