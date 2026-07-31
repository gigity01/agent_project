"""文档模块 HTTP Router 的兼容导出。"""

from app.modules.document.presentation.dependencies import document_upload_form
from app.modules.document.presentation.router import router


__all__ = ["document_upload_form", "router"]
