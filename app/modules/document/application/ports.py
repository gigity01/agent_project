"""文档应用层使用的外部能力 Port 与运行时装配点。"""

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
    """由 Bootstrap 提供给文档用例的具体外部能力。"""

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


_ports: DocumentApplicationPorts | None = None


def configure_document_ports(ports: DocumentApplicationPorts) -> None:
    """由 Bootstrap 在应用启动时装配文档外部能力。"""

    global _ports
    _ports = ports


def _get_ports() -> DocumentApplicationPorts:
    if _ports is None:
        raise RuntimeError("文档应用 Port 尚未装配")
    return _ports


def create_uow() -> Any:
    return _get_ports().uow_factory()


def create_document(**values: Any) -> Any:
    return _get_ports().document_factory(**values)


def create_parent_block(**values: Any) -> Any:
    return _get_ports().parent_block_factory(**values)


def create_child_chunk(**values: Any) -> Any:
    return _get_ports().child_chunk_factory(**values)


def get_processor(source_type: str) -> Any:
    return _get_ports().processor_factory(source_type)


def get_chunker(source_type: str) -> Any:
    return _get_ports().chunker_factory(source_type)


def create_embedding_client() -> Any:
    return _get_ports().embedding_factory()


def create_vector_store() -> Any:
    return _get_ports().vector_store_factory()


def create_docling_client() -> Any:
    return _get_ports().docling_factory()


def create_vector_point(**values: Any) -> Any:
    return _get_ports().point_factory(**values)


def validate_content_type(file: UploadFilePort) -> None:
    _get_ports().validate_content_type(file)


def get_safe_extension(filename: str) -> str:
    return _get_ports().get_safe_extension(filename)


def calculate_file_hash(path: Path) -> str:
    return _get_ports().calculate_file_hash(path)


def cleanup_file(path: Path) -> bool:
    return _get_ports().cleanup_file(path)


def is_integrity_error(exc: BaseException) -> bool:
    return isinstance(exc, _get_ports().integrity_error_type)
