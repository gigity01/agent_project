"""文档模块切块辅助函数的兼容导出。"""

from app.modules.document.infrastructure.chunking.common import (
    CSV_CHILD_MAX_CHARS,
    CSV_PARENT_MAX_CHARS,
    CSV_PARENT_MAX_ROWS,
    PARENT_BLOCK_MAX_CHARS,
    build_embedding_text,
    md5_text,
    normalize_text,
    split_paragraphs,
    split_text_to_child_chunks,
    split_text_to_parent_segments,
)

__all__ = [
    "CSV_CHILD_MAX_CHARS",
    "CSV_PARENT_MAX_CHARS",
    "CSV_PARENT_MAX_ROWS",
    "PARENT_BLOCK_MAX_CHARS",
    "build_embedding_text",
    "md5_text",
    "normalize_text",
    "split_paragraphs",
    "split_text_to_child_chunks",
    "split_text_to_parent_segments",
]
