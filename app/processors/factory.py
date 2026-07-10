# app/processors/factory.py

from fastapi import HTTPException

from app.integrations.document_converter.docling_client import DoclingClient
from app.policies.document_source_policy import (
    EXTERNAL_PROCESS_SOURCE_TYPES,
    LOCAL_PROCESS_SOURCE_TYPES,
    get_expected_process_output_type,
    normalize_source_type,
)
from app.processors.base import BaseProcessor
from app.processors.csv_processor import CsvProcessor
from app.processors.external_markdown_processor import ExternalMarkdownProcessor
from app.processors.md_processor import MdProcessor
from app.processors.txt_processor import TxtProcessor


PROCESSOR_MAP: dict[str, type[BaseProcessor]] = {
    "txt": TxtProcessor,
    "md": MdProcessor,
    "csv": CsvProcessor,
}


def get_processor(source_type: str) -> BaseProcessor:
    normalized_source_type = normalize_source_type(source_type)

    if normalized_source_type in EXTERNAL_PROCESS_SOURCE_TYPES:
        return ExternalMarkdownProcessor(
            source_type=normalized_source_type,
            client=DoclingClient(),
        )

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
    normalized_source_type = normalize_source_type(source_type)

    if normalized_source_type in EXTERNAL_PROCESS_SOURCE_TYPES:
        return "md"

    if normalized_source_type in LOCAL_PROCESS_SOURCE_TYPES:
        return normalized_source_type

    raise HTTPException(
        status_code=400,
        detail=f"当前暂不支持处理该文件类型: {source_type}",
    )
