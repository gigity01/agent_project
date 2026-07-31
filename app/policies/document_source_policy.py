"""文档源类型策略的兼容导出。"""

from app.modules.document.domain.policies import (
    EXTERNAL_PROCESS_SOURCE_TYPES,
    LOCAL_PROCESS_SOURCE_TYPES,
    SOURCE_TYPE_ALIASES,
    get_expected_process_output_type,
    normalize_source_type,
    requires_external_processing,
)

__all__ = [
    "EXTERNAL_PROCESS_SOURCE_TYPES",
    "LOCAL_PROCESS_SOURCE_TYPES",
    "SOURCE_TYPE_ALIASES",
    "get_expected_process_output_type",
    "normalize_source_type",
    "requires_external_processing",
]
