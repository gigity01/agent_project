from fastapi import HTTPException

from app.chunkers.base import BaseChunker
from app.chunkers.text_chunker import TextChunker
from app.chunkers.markdown_chunker import MarkdownChunker
from app.policies.document_source_policy import normalize_source_type


def get_chunker(source_type: str) -> BaseChunker:
    chunkers: dict[str, BaseChunker] = {
        "txt": TextChunker(),
        "md": MarkdownChunker(),
    }

    normalized_source_type = normalize_source_type(source_type)
    chunker = chunkers.get(normalized_source_type)

    if chunker is None:
        raise HTTPException(
            status_code=400,
            detail=f"当前暂不支持该文件类型切块: {source_type}",
        )

    return chunker
