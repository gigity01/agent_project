"""文档模块按本地源类型选择清洗处理器。"""

from fastapi import HTTPException

from app.modules.document.domain.policies import normalize_source_type
from app.modules.document.infrastructure.parsing.base import BaseProcessor
from app.modules.document.infrastructure.parsing.csv import CsvProcessor
from app.modules.document.infrastructure.parsing.markdown import MdProcessor
from app.modules.document.infrastructure.parsing.text import TxtProcessor


PROCESSOR_MAP: dict[str, type[BaseProcessor]] = {
    "txt": TxtProcessor,
    "md": MdProcessor,
    "csv": CsvProcessor,
}


def get_processor(source_type: str) -> BaseProcessor:
    """返回可处理指定源类型的处理器，不支持时抛出 HTTP 400。"""
    normalized_source_type = normalize_source_type(source_type)

    processor_cls = PROCESSOR_MAP.get(normalized_source_type)

    if processor_cls is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"当前暂不支持处理该文件类型: {source_type}。"
                "请联系上级管理员，或按照知识库管理规则转换为支持的文件类型后再上传。"
            ),
        )

    return processor_cls()


def get_processor_output_type(source_type: str) -> str:
    """返回指定源类型经处理后应落盘的文件类型。"""
    normalized_source_type = normalize_source_type(source_type)

    if normalized_source_type in PROCESSOR_MAP:
        return normalized_source_type

    raise HTTPException(
        status_code=400,
        detail=f"当前暂不支持处理该文件类型: {source_type}",
    )
