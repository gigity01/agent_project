from datetime import datetime
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config.settings import (
    RAW_STORAGE_DIR,
    MAX_UPLOAD_FILE_SIZE,
    DEFAULT_DOCUMENT_STATUS,
    DEFAULT_DOCUMENT_VERSION,
    DEFAULT_CREATED_BY_ACTOR_CODE,
    DOCUMENT_CODE_PREFIX,
    DOCUMENT_CODE_RANDOM_LENGTH,
)
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentUploadFormData
from app.utils.file_security import (
    get_safe_extension,
    validate_content_type,
    calculate_file_hash,
)


def generate_doc_code() -> str:
    now = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = uuid4().hex[:DOCUMENT_CODE_RANDOM_LENGTH].upper()
    return f"{DOCUMENT_CODE_PREFIX}_{now}_{random_part}"


async def save_uploaded_document(
    db: Session,
    file: UploadFile,
    meta: DocumentUploadFormData,
    created_by_actor_code: str | None = None,
) -> Document:
    if not file.filename:
        raise HTTPException(status_code=400, detail="必须上传文件")

    validate_content_type(file)



    source_type = get_safe_extension(file.filename)
    doc_code = generate_doc_code()

    RAW_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    saved_filename = f"{doc_code}.{source_type}"
    save_path = RAW_STORAGE_DIR / saved_filename

    total_size = 0

    try:
        with save_path.open("wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)

                if not chunk:
                    break

                total_size += len(chunk)

                if total_size > MAX_UPLOAD_FILE_SIZE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"文件超过 {MAX_UPLOAD_FILE_SIZE // 1024 // 1024}MB 限制",
                    )

                buffer.write(chunk)

    except Exception:
        if save_path.exists():
            save_path.unlink()
        raise

    if total_size == 0:
        if save_path.exists():
            save_path.unlink()
        raise HTTPException(status_code=400, detail="不能上传空文件")

    content_hash = calculate_file_hash(save_path)

    repo = DocumentRepository(db)

    duplicated = repo.get_by_hash_in_kb(
        kb_id=meta.kb_id,
        content_hash=content_hash,
    )

    if duplicated:
        save_path.unlink(missing_ok=True)
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
        created_by_actor_code=created_by_actor_code or DEFAULT_CREATED_BY_ACTOR_CODE,
        indexed_at=None,
    )

    try:
        return repo.create(document)
    except Exception:
        save_path.unlink(missing_ok=True)
        raise