"""文档模块本地文件工具的兼容导出。"""

from app.modules.document.infrastructure.storage.local import (
    calculate_file_hash,
    get_safe_extension,
    validate_content_type,
    validate_filename,
)

__all__ = [
    "calculate_file_hash",
    "get_safe_extension",
    "validate_content_type",
    "validate_filename",
]
