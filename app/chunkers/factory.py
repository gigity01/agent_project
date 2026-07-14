"""根据标准化后的文件类型选择对应切块器。"""

from fastapi import HTTPException

from app.chunkers.base import BaseChunker
from app.chunkers.csv_chunker import CsvChunker
from app.chunkers.text_chunker import TextChunker
from app.chunkers.markdown_chunker import MarkdownChunker
from app.policies.document_source_policy import normalize_source_type


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
