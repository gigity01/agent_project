"""编排文件落盘、去重、文档建档和上传审计日志。"""

from datetime import datetime
from uuid import uuid4
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.app_config.settings import (
    RAW_LOCAL_STORAGE_DIR,
    RAW_EXTERNAL_STORAGE_DIR,
    MAX_UPLOAD_FILE_SIZE,
    DEFAULT_DOCUMENT_STATUS,
    DEFAULT_DOCUMENT_VERSION,
    DEFAULT_CREATED_BY_ACTOR_CODE,
    DOCUMENT_CODE_PREFIX,
    DOCUMENT_CODE_RANDOM_LENGTH,
)
from app.models.document import Document
from app.policies.document_source_policy import (
    normalize_source_type,
    requires_external_processing,
)
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentUploadFormData
from core.observability.document_upload_logger import DocumentUploadLogger
from main_utils.file_cleanup import cleanup_file
from app.app_utils.file_security import (
    get_safe_extension,
    validate_content_type,
    calculate_file_hash,
)


READ_CHUNK_SIZE = 1024 * 1024

def generate_doc_code() -> str:
    """生成带时间戳和随机后缀的文档业务编号。"""
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = uuid4().hex[:DOCUMENT_CODE_RANDOM_LENGTH].upper()
    return f"{DOCUMENT_CODE_PREFIX}_{now}_{random_part}"

def get_raw_storage_dir(source_type: str):
    """按处理路径返回原始文件的本地存储目录。"""
    if requires_external_processing(source_type):
        return RAW_EXTERNAL_STORAGE_DIR

    return RAW_LOCAL_STORAGE_DIR

async def save_uploaded_document(
    db: Session,
    file: UploadFile,
    meta: DocumentUploadFormData,
    created_by_actor_code: str | None = None,
) -> Document:
    """保存上传文件、校验内容去重，并创建 draft 状态文档。

    任一步骤失败时会清理已落盘的原始文件，并写入对应审计日志。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="必须上传文件")

    validate_content_type(file)

    source_extension = get_safe_extension(file.filename)
    source_type = normalize_source_type(source_extension)
    doc_code = generate_doc_code()

    actor_code = created_by_actor_code or DEFAULT_CREATED_BY_ACTOR_CODE

    # 两个目录都会预创建：选择由 source_type 决定，避免在校验通过后因目录
    # 不存在而中断上传流程。
    RAW_EXTERNAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    RAW_LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    saved_filename = f"{doc_code}.{source_extension}"
    save_path = get_raw_storage_dir(source_type) / saved_filename
    total_size = 0
    upload_logger = DocumentUploadLogger()

    upload_logger.started(
        doc_code=doc_code,
        kb_id=meta.kb_id,
        domain_code=meta.domain_code,
        business_scene=meta.business_scene,
        title=meta.title,
        filename=file.filename,
        source_type=source_type,
        saved_filename=saved_filename,
        created_by_actor_code=actor_code,
    )

    try:
        with save_path.open("wb") as buffer:
            while True:
                chunk = await file.read(READ_CHUNK_SIZE)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_UPLOAD_FILE_SIZE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"文件超过 {MAX_UPLOAD_FILE_SIZE // 1024 // 1024}MB 限制",
                    )

                buffer.write(chunk)

        if total_size == 0:
            raise HTTPException(status_code=400, detail="不能上传空文件")

        upload_logger.raw_file_saved(
            doc_code=doc_code,
            kb_id=meta.kb_id,
            source_uri=str(save_path),
            file_size=total_size,
        )

        # 先完整落盘再计算哈希，保证去重比较的是实际保存的字节，而非分块读取的
        # 中间状态。
        content_hash = calculate_file_hash(save_path)

        upload_logger.hash_calculated(
            doc_code=doc_code,
            kb_id=meta.kb_id,
            content_hash=content_hash,
        )

        repo = DocumentRepository(db)

        # 去重范围限定在知识库内：不同知识库可各自维护相同原件。
        duplicated = repo.get_by_hash_in_kb(
            kb_id=meta.kb_id,
            content_hash=content_hash,
        )

        if duplicated:

            upload_logger.duplicate_detected(
                doc_code=doc_code,
                kb_id=meta.kb_id,
                content_hash=content_hash,
                duplicated_document=duplicated,
            )

            raise HTTPException(
                status_code=409,
                detail=f"该知识库下已存在相同内容文档: {duplicated.doc_code}",
            )

        document = Document(
            doc_code=doc_code,
            kb_id=meta.kb_id,
            domain_code=meta.domain_code,
            business_scene=meta.business_scene,
            title=meta.title,
            original_filename=file.filename,
            file_size=total_size,
            source_type=source_type,
            source_uri=str(save_path),
            cleaned_uri=None,
            content_hash=content_hash,
            version=DEFAULT_DOCUMENT_VERSION,
            status=DEFAULT_DOCUMENT_STATUS,
            replaced_by=None,
            risk_level=meta.risk_level,
            effective_at=meta.effective_at,
            expired_at=meta.expired_at,
            created_by_actor_code=actor_code,
            indexed_at=None,
        )

        created_document = repo.create(document)
        db.commit()
        db.refresh(created_document)
        upload_logger.completed(document=created_document)

        return created_document

    except HTTPException as exc:
        # 业务拒绝（格式、大小、重复等）同样可能已创建临时原件，必须清理。
        cleanup_success = cleanup_file(save_path)
        upload_logger.failed_by_http_exception(
            exc=exc,
            doc_code=doc_code,
            kb_id=meta.kb_id,
            domain_code=meta.domain_code,
            business_scene=meta.business_scene,
            title=meta.title,
            filename=file.filename,
            source_type=source_type,
            source_uri=str(save_path),
            file_size=total_size,
            cleanup_success=cleanup_success,
        )
        raise

    except Exception as exc:
        cleanup_success = cleanup_file(save_path)

        upload_logger.failed_by_unexpected_exception(
            exc=exc,
            doc_code=doc_code,
            kb_id=meta.kb_id,
            domain_code=meta.domain_code,
            business_scene=meta.business_scene,
            title=meta.title,
            filename=file.filename,
            source_type=source_type,
            source_uri=str(save_path),
            file_size=total_size,
            cleanup_success=cleanup_success,
        )

        raise
