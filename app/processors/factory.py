"""文档模块 Processor Factory 的兼容导出。"""

from app.modules.document.infrastructure.parsing.factory import (
    get_processor,
    get_processor_output_type,
)

__all__ = ["get_processor", "get_processor_output_type"]
