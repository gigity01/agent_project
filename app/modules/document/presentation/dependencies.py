"""文档 Presentation 层的 FastAPI 依赖。"""

from datetime import datetime
from typing import Literal

from fastapi import Depends, Form

from app.bootstrap.container import AppContainer
from app.bootstrap.dependencies import get_container
from app.modules.document.application.use_cases.build_chunks import (
    BuildChunksUseCase,
)
from app.modules.document.application.use_cases.index_vectors import (
    IndexVectorsUseCase,
)
from app.modules.document.application.use_cases.process_document import (
    ProcessDocumentUseCase,
)
from app.modules.document.application.use_cases.upload_document import (
    UploadDocumentUseCase,
)
from app.modules.document.presentation.schemas import DocumentUploadFormData


def document_upload_form(
    title: str = Form(...),
    kb_id: int = Form(...),
    domain_code: str = Form(...),
    business_scene: str | None = Form(None),
    risk_level: Literal["low", "medium", "high", "critical"] = Form("low"),
    effective_at: datetime | None = Form(None),
    expired_at: datetime | None = Form(None),
) -> DocumentUploadFormData:
    """将 multipart 表单字段组装为上传用例使用的元数据对象。"""
    return DocumentUploadFormData(
        title=title,
        kb_id=kb_id,
        domain_code=domain_code,
        business_scene=business_scene,
        risk_level=risk_level,
        effective_at=effective_at,
        expired_at=expired_at,
    )


def get_upload_document_use_case(
    container: AppContainer = Depends(get_container),
) -> UploadDocumentUseCase:
    return container.upload_document


def get_process_document_use_case(
    container: AppContainer = Depends(get_container),
) -> ProcessDocumentUseCase:
    return container.process_document


def get_build_chunks_use_case(
    container: AppContainer = Depends(get_container),
) -> BuildChunksUseCase:
    return container.build_chunks


def get_index_vectors_use_case(
    container: AppContainer = Depends(get_container),
) -> IndexVectorsUseCase:
    return container.index_vectors
