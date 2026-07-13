"""为复杂文件生成可交给本地处理器的二级 Markdown 源。"""

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.app_config.settings import SECONDARY_TEXT_STORAGE_DIR
from app.integrations.document_converter.docling_client import DoclingClient
from app.models.document import Document
from app.models.document_artifact import DocumentArtifact
from app.policies.document_source_policy import (
    normalize_source_type,
    requires_external_processing,
)
from app.repositories.document_artifact_repository import DocumentArtifactRepository
from app.schemas.document_artifact import DocumentArtifactCreate
from app.utils.file_security import calculate_file_hash


@dataclass(frozen=True)
class PreparedProcessSource:
    """供处理器使用的标准化输入文件及其派生产物信息。"""

    source_path: Path
    source_type: str
    generated_secondary_text: bool = False
    artifact: DocumentArtifact | None = None

    def cleanup_generated_file(self) -> None:
        """仅在后续事务失败时删除本次生成的二级文本文件。"""
        if self.generated_secondary_text:
            self.source_path.unlink(missing_ok=True)


def prepare_process_source(
    *,
    db: Session,
    document: Document,
    source_path: Path,
) -> PreparedProcessSource:
    """将外部格式转换为二级 Markdown，或直接返回本地源文件。

    本函数只执行 `flush()` 范围内的 Artifact 变更；调用方负责提交或回滚事务。
    """
    source_type = normalize_source_type(document.source_type)

    # 本地可处理格式不生成二级产物，避免无意义复制并保留原件作为处理输入。
    if not requires_external_processing(source_type):
        return PreparedProcessSource(
            source_path=source_path,
            source_type=source_type,
        )

    markdown_result = DoclingClient().convert_to_markdown(
        source_path=source_path,
        source_type=source_type,
    )
    SECONDARY_TEXT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    artifact_code = _generate_artifact_code(document.doc_code)
    secondary_path = SECONDARY_TEXT_STORAGE_DIR / f"{artifact_code}.md"

    try:
        secondary_path.write_text(markdown_result.markdown, encoding="utf-8")
        artifact_repository = DocumentArtifactRepository(db)

        # 同一用途只保留一个 active 产物，旧版本仍留在库中用于审计和回溯。
        artifact_repository.mark_active_as_superseded(
            document_id=document.id,
            artifact_type="secondary_text",
            artifact_role="process_input",
            artifact_format="md",
        )
        artifact = artifact_repository.create(
            DocumentArtifactCreate(
                document_id=document.id,
                artifact_code=artifact_code,
                artifact_type="secondary_text",
                artifact_role="process_input",
                artifact_format="md",
                artifact_uri=str(secondary_path),
                artifact_hash=calculate_file_hash(secondary_path),
                provider=markdown_result.provider,
                processor=DoclingClient.__name__,
                file_size=secondary_path.stat().st_size,
                char_count=len(markdown_result.markdown),
                line_count=len(markdown_result.markdown.splitlines()),
                status="active",
                metadata=markdown_result.metadata,
                created_by_actor_code=document.created_by_actor_code,
            )
        )
    except Exception:
        # 文件系统不受数据库事务管理；持久化失败时显式删除本次新生成的孤儿文件。
        secondary_path.unlink(missing_ok=True)
        raise

    return PreparedProcessSource(
        source_path=secondary_path,
        source_type="md",
        generated_secondary_text=True,
        artifact=artifact,
    )


def _generate_artifact_code(doc_code: str) -> str:
    """生成不超过 Artifact 字段长度的唯一业务编号。"""
    suffix = f"_ART_DOCLING_MD_{uuid4().hex[:12].upper()}"
    return f"{doc_code[:100 - len(suffix)]}{suffix}"
