"""文档 Presentation 层的 FastAPI 依赖。"""

from datetime import datetime
from typing import Literal

from fastapi import Form

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
