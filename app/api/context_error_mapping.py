"""Context HTTP 错误映射兼容导出。"""

from app.modules.context.presentation.router import (
    _to_http_exception as to_context_http_exception,
)


__all__ = ["to_context_http_exception"]
