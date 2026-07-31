"""文档 HTTP Schema 的兼容导出。"""

from app.modules.document.presentation.schemas import (
    DocumentProcessResponse,
    DocumentResponse,
    DocumentUploadFormData,
    RiskLevel,
)


__all__ = [
    "DocumentProcessResponse",
    "DocumentResponse",
    "DocumentUploadFormData",
    "RiskLevel",
]
