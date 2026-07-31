"""文档模块按标准化文件类型选择切块器。"""

from fastapi import HTTPException

from app.modules.document.domain.policies import normalize_source_type
from app.modules.document.infrastructure.chunking.base import BaseChunker
from app.modules.document.infrastructure.chunking.csv import CsvChunker
from app.modules.document.infrastructure.chunking.markdown import MarkdownChunker
from app.modules.document.infrastructure.chunking.text import TextChunker


def get_chunker(source_type: str) -> BaseChunker:
    """返回文件类型对应的切块策略，不支持时返回客户端错误。"""
    chunkers: dict[str, BaseChunker] = {
        "txt": TextChunker(),
        "md": MarkdownChunker(),
        "csv": CsvChunker(),
    }

    normalized_source_type = normalize_source_type(source_type)
    chunker = chunkers.get(normalized_source_type)

    if chunker is None:
        raise HTTPException(
            status_code=400,
            detail=f"当前暂不支持该文件类型切块: {source_type}",
        )

    return chunker
