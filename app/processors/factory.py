# app/processors/factory.py

from fastapi import HTTPException

from app.processors.base import BaseProcessor
from app.processors.txt_processor import TxtProcessor
from app.processors.md_processor import MdProcessor
from app.processors.csv_processor import CsvProcessor


PROCESSOR_MAP: dict[str, type[BaseProcessor]] = {
    "txt": TxtProcessor,
    "md": MdProcessor,
    "csv": CsvProcessor,
}


def get_processor(source_type: str) -> BaseProcessor:
    normalized_source_type = source_type.lower().strip()

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