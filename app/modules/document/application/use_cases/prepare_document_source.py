"""为复杂文档生成可交给本地处理器的二级 Markdown 源。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from app.modules.document.application.ports import DocumentApplicationPorts
from app.modules.document.application.settings import (
    DocumentProcessingSettings,
)
from app.modules.document.domain.policies import (
    normalize_source_type,
    requires_external_processing,
)

if TYPE_CHECKING:
    from app.modules.document.application.use_cases.process_document import (
        ProcessingContext,
    )


@dataclass(frozen=True)
class PendingArtifact:
    """事务外生成、等待在完成事务中登记的派生产物元数据。"""

    artifact_type: str
    artifact_role: str
    artifact_format: str
    artifact_uri: str
    artifact_hash: str
    provider: str | None
    processor: str | None
    file_size: int
    char_count: int
    line_count: int
    metadata: dict[str, Any] | None


@dataclass(frozen=True)
class PreparedProcessSource:
    """供处理器使用的标准化输入文件及其待登记产物信息。"""

    source_path: Path
    source_type: str
    generated_secondary_text: bool = False
    secondary_artifact: PendingArtifact | None = None

def prepare_process_source(
    document: ProcessingContext,
    *,
    ports: DocumentApplicationPorts,
    settings: DocumentProcessingSettings,
    output_dir: Path,
) -> PreparedProcessSource:
    """在事务外转换复杂格式并返回内存产物，不访问数据库。"""
    source_type = normalize_source_type(document.source_type)

    # 本地可处理格式不生成二级产物，保留原件作为处理输入。
    if not requires_external_processing(source_type):
        return PreparedProcessSource(
            source_path=document.source_path,
            source_type=source_type,
        )

    docling_client = ports.docling_factory()
    markdown_result = docling_client.convert_to_markdown(
        source_path=document.source_path,
        source_type=source_type,
    )
    del settings
    output_dir.mkdir(parents=True, exist_ok=True)

    artifact_code = _generate_artifact_code(document.doc_code)
    secondary_path = output_dir / f"{artifact_code}.md"

    secondary_path.write_text(markdown_result.markdown, encoding="utf-8")
    pending_artifact = PendingArtifact(
        artifact_type="secondary_text",
        artifact_role="process_input",
        artifact_format="md",
        artifact_uri=str(secondary_path),
        artifact_hash=ports.calculate_file_hash(secondary_path),
        provider=markdown_result.provider,
        processor=docling_client.__class__.__name__,
        file_size=secondary_path.stat().st_size,
        char_count=len(markdown_result.markdown),
        line_count=len(markdown_result.markdown.splitlines()),
        metadata=markdown_result.metadata,
    )

    return PreparedProcessSource(
        source_path=secondary_path,
        source_type="md",
        generated_secondary_text=True,
        secondary_artifact=pending_artifact,
    )


def _generate_artifact_code(doc_code: str) -> str:
    """生成不超过 Artifact 字段长度的唯一业务编号。"""
    suffix = f"_ART_DOCLING_MD_{uuid4().hex[:12].upper()}"
    return f"{doc_code[:100 - len(suffix)]}{suffix}"
