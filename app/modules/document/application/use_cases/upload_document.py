"""上传文档应用用例：编排落盘、去重、建档和审计日志。"""

import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.config.settings import (
    RAW_LOCAL_STORAGE_DIR,
    RAW_EXTERNAL_STORAGE_DIR,
    MAX_UPLOAD_FILE_SIZE,
    DEFAULT_DOCUMENT_STATUS,
    DEFAULT_DOCUMENT_VERSION,
    DEFAULT_CREATED_BY_ACTOR_CODE,
    DOCUMENT_CODE_PREFIX,
    DOCUMENT_CODE_RANDOM_LENGTH,
)
from app.modules.document.application.dto import DocumentResult
from app.modules.document.application.errors import (
    DocumentApplicationError as HTTPException,
)
from app.modules.document.application.ports import (
    UploadFilePort,
    UploadMetadataPort,
    calculate_file_hash,
    cleanup_file,
    create_document as Document,
    create_uow as SQLAlchemyUnitOfWork,
    get_safe_extension,
    is_integrity_error,
    validate_content_type,
)
from app.modules.document.domain.enums import (
    DocumentLifecycleStatus,
    DocumentStorageStatus,
)
from app.modules.document.domain.policies import (
    normalize_source_type,
    requires_external_processing,
)
from app.shared.observability.document_upload_logger import (
    DocumentUploadLogger,
)


READ_CHUNK_SIZE = 1024 * 1024
DOCUMENT_CONTENT_UNIQUE_CONSTRAINT = "uq_documents_kb_active_content_hash"
logger = logging.getLogger(__name__)


def is_duplicate_content_error(exc: BaseException) -> bool:
    """判断完整性错误是否来自知识库内的内容唯一约束。"""
    error_message = str(exc.orig).lower()
    return (
        DOCUMENT_CONTENT_UNIQUE_CONSTRAINT.lower() in error_message
        or (
            "documents.kb_id" in error_message
            and "documents.active_content_hash" in error_message
        )
    )


def safe_log_completed(
    upload_logger: DocumentUploadLogger,
    document: Document,
) -> None:
    """尽力记录上传完成事件，不让观测故障破坏已提交的主营业务。"""
    try:
        upload_logger.completed(document=document)
    except Exception:
        logger.exception(
            "文档上传已提交，但完成事件写入失败",
            extra={
                "document_id": document.id,
                "doc_code": document.doc_code,
            },
        )


def get_initial_lifecycle_status(effective_at: datetime | None) -> str:
    """根据生效时间确定新文档初始业务生命周期。"""
    if effective_at is None:
        return DocumentLifecycleStatus.ACTIVE.value

    now = datetime.now(tz=effective_at.tzinfo)
    if effective_at > now:
        return DocumentLifecycleStatus.SCHEDULED.value

    return DocumentLifecycleStatus.ACTIVE.value


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
    file: UploadFilePort,
    meta: UploadMetadataPort,
    created_by_actor_code: str | None = None,
) -> DocumentResult:
    """保存上传文件、校验内容去重，并创建 draft 状态文档。

    任一步骤失败时会清理已落盘的原始文件，并写入对应审计日志。
    """
    upload_logger = DocumentUploadLogger()
    actor_code = created_by_actor_code or DEFAULT_CREATED_BY_ACTOR_CODE
    phase = "validate"
    doc_code: str | None = None
    source_type: str | None = None
    save_path: Path | None = None
    total_size = 0
    db_committed = False

    try:
        doc_code = generate_doc_code()
        if not file.filename:
            raise HTTPException(status_code=400, detail="必须上传文件")

        validate_content_type(file)
        source_extension = get_safe_extension(file.filename)
        source_type = normalize_source_type(source_extension)

        phase = "prepare_storage"
        # 两个目录都会预创建：选择由 source_type 决定，避免在校验通过后因
        # 目录不存在而中断上传流程。
        RAW_EXTERNAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        RAW_LOCAL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        saved_filename = f"{doc_code}.{source_extension}"
        save_path = get_raw_storage_dir(source_type) / saved_filename

        phase = "execute"
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

        phase = "finalize"
        with SQLAlchemyUnitOfWork() as uow:
            # 去重范围限定在知识库内：不同知识库可各自维护相同原件。
            duplicated = uow.documents.get_active_by_hash_in_kb(
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
                    detail=f"已存在相同有效文件: {duplicated.doc_code}",
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
                active_content_hash=content_hash,
                lifecycle_status=get_initial_lifecycle_status(meta.effective_at),
                storage_status=DocumentStorageStatus.ACTIVE.value,
                version=DEFAULT_DOCUMENT_VERSION,
                status=DEFAULT_DOCUMENT_STATUS,
                replaced_by=None,
                risk_level=meta.risk_level,
                effective_at=meta.effective_at,
                expired_at=meta.expired_at,
                created_by_actor_code=actor_code,
                indexed_at=None,
            )

            try:
                created_document = uow.documents.create(document)
                created_response = DocumentResult.model_validate(created_document)

                # commit 必须是 UoW 内最后一个数据库动作。
                uow.commit()
            except Exception as exc:
                if is_integrity_error(exc) and is_duplicate_content_error(exc):
                    raise HTTPException(
                        status_code=409,
                        detail="该知识库中已存在相同有效文件",
                    ) from exc
                raise

            db_committed = True

        safe_log_completed(upload_logger, created_document)

        return created_response

    except HTTPException as exc:
        if db_committed:
            raise

        # 业务拒绝（格式、大小、重复等）同样可能已创建临时原件，必须清理。
        cleanup_success = (
            cleanup_file(save_path) if save_path is not None else True
        )
        upload_logger.failed_by_http_exception(
            exc=exc,
            phase=phase,
            doc_code=doc_code,
            kb_id=meta.kb_id,
            domain_code=meta.domain_code,
            business_scene=meta.business_scene,
            title=meta.title,
            filename=file.filename,
            source_type=source_type,
            source_uri=str(save_path) if save_path is not None else None,
            file_size=total_size,
            cleanup_success=cleanup_success,
        )
        raise

    except Exception as exc:
        if db_committed:
            logger.exception(
                "文档上传已提交，后续操作失败但保留原始文件",
                extra={"doc_code": doc_code},
            )
            raise

        cleanup_success = (
            cleanup_file(save_path) if save_path is not None else True
        )

        upload_logger.failed_by_unexpected_exception(
            exc=exc,
            phase=phase,
            doc_code=doc_code,
            kb_id=meta.kb_id,
            domain_code=meta.domain_code,
            business_scene=meta.business_scene,
            title=meta.title,
            filename=file.filename,
            source_type=source_type,
            source_uri=str(save_path) if save_path is not None else None,
            file_size=total_size,
            cleanup_success=cleanup_success,
        )

        raise
