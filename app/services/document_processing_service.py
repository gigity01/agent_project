"""编排原始文档清洗，并维护文档处理状态。"""

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.app_config.settings import CLEANED_STORAGE_DIR
from app.repositories.document_repository import DocumentRepository
from app.processors.factory import get_processor
from app.schemas.document import DocumentProcessResponse


def process_document(
    db: Session,
    document_id: int,
) -> DocumentProcessResponse:
    """处理 draft 或 failed 文档，成功后将其置为 active。

    清洗失败会删除本次产生的文件，并将文档状态恢复为 failed。
    """
    repo = DocumentRepository(db)

    document = repo.get_by_id(document_id)

    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")

    if document.status not in ["draft", "failed"]:
        raise HTTPException(
            status_code=400,
            detail=f"当前文档状态不允许处理: {document.status}",
        )

    source_path = Path(document.source_uri)

    if not source_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"原始文件不存在: {document.source_uri}",
        )

    if not source_path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"原始路径不是有效文件: {document.source_uri}",
        )
    CLEANED_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    cleaned_filename = f"{document.doc_code}.cleaned.{document.source_type}"
    cleaned_path = CLEANED_STORAGE_DIR / cleaned_filename
    repo.update_status(document, "indexing")

    try:
        processor = get_processor(document.source_type)

        processor.process(
            source_path=source_path,
            cleaned_path=cleaned_path,
        )

        updated_document = repo.update_cleaned_uri(
            document=document,
            cleaned_uri=str(cleaned_path),
            status="active",
        )

        return DocumentProcessResponse(
            document_id=updated_document.id,
            doc_code=updated_document.doc_code,
            source_type=updated_document.source_type,
            source_uri=updated_document.source_uri,
            cleaned_uri=updated_document.cleaned_uri,
            status=updated_document.status,
        )
    except HTTPException:
        cleaned_path.unlink(missing_ok=True)
        repo.update_status(document, "failed")
        raise

    except Exception as e:
        cleaned_path.unlink(missing_ok=True)
        repo.update_status(document, "failed")
        raise HTTPException(
            status_code=500,
            detail=f"文档处理失败: {str(e)}",
        )
