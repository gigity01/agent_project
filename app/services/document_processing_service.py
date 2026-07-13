"""编排原始文件准备、清洗与文档处理状态更新。"""

from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.app_config.settings import CLEANED_STORAGE_DIR
from app.constants.document_status import DocumentStatus
from app.repositories.document_repository import DocumentRepository
from app.processors.factory import get_processor
from app.schemas.document import DocumentProcessResponse
from app.services.document_source_prepare_service import prepare_process_source
from core.observability.document_process_logger import DocumentProcessLogger


def process_document(
    db: Session,
    document_id: int,
) -> DocumentProcessResponse:
    """处理 draft 或 failed 文档，成功后将其置为 processed。

    复杂文件会先生成并登记二级 Markdown，再复用 MdProcessor；失败时回滚
    Artifact 事务并清理本次生成的文件，客户端只收到通用错误信息。
    """
    repo = DocumentRepository(db)

    document = repo.get_by_id(document_id)

    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")

    if document.status not in {
        DocumentStatus.UPLOADED.value,
        DocumentStatus.FAILED.value,
    }:
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
    process_logger = DocumentProcessLogger()
    process_logger.started(
        document_id=document.id,
        doc_code=document.doc_code,
        source_type=document.source_type,
    )
    document.status = DocumentStatus.PROCESSING.value
    db.commit()

    prepared_source = None
    cleaned_path = None

    try:
        prepared_source = prepare_process_source(
            db=db,
            document=document,
            source_path=source_path,
        )
        CLEANED_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        cleaned_filename = (
            f"{document.doc_code}.cleaned.{prepared_source.source_type}"
        )
        cleaned_path = CLEANED_STORAGE_DIR / cleaned_filename
        processor = get_processor(prepared_source.source_type)

        processor.process(
            source_path=prepared_source.source_path,
            cleaned_path=cleaned_path,
        )

        document.cleaned_uri = str(cleaned_path)
        document.status = DocumentStatus.PROCESSED.value
        db.commit()
        db.refresh(document)
        process_logger.completed(
            document_id=document.id,
            doc_code=document.doc_code,
            processed_source_type=prepared_source.source_type,
            cleaned_uri=document.cleaned_uri,
        )

        return DocumentProcessResponse(
            document_id=document.id,
            doc_code=document.doc_code,
            source_type=document.source_type,
            source_uri=document.source_uri,
            cleaned_uri=document.cleaned_uri,
            status=document.status,
        )
    except HTTPException as exc:
        _mark_processing_failed(
            db=db,
            repo=repo,
            document_id=document_id,
            cleaned_path=cleaned_path,
            prepared_source=prepared_source,
        )
        process_logger.failed(
            document_id=document.id,
            doc_code=document.doc_code,
            error=exc,
        )
        raise

    except Exception as exc:
        _mark_processing_failed(
            db=db,
            repo=repo,
            document_id=document_id,
            cleaned_path=cleaned_path,
            prepared_source=prepared_source,
        )
        process_logger.failed(
            document_id=document.id,
            doc_code=document.doc_code,
            error=exc,
        )
        raise HTTPException(
            status_code=500,
            detail="文档处理失败，请稍后重试或联系管理员",
        ) from exc


def _mark_processing_failed(
    *,
    db: Session,
    repo: DocumentRepository,
    document_id: int,
    cleaned_path: Path | None,
    prepared_source,
) -> None:
    """回滚本次事务、清理临时文件，并将文档置为 failed。"""
    db.rollback()

    if cleaned_path is not None:
        cleaned_path.unlink(missing_ok=True)

    if prepared_source is not None:
        prepared_source.cleanup_generated_file()

    failed_document = repo.get_by_id(document_id)
    if failed_document is not None:
        failed_document.status = DocumentStatus.FAILED.value
        db.commit()
