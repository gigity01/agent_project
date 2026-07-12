"""文档派生产物的类型枚举。"""

from enum import StrEnum


class DocumentArtifactType(StrEnum):
    """区分二级文本、清洗文本、布局与多媒体提取产物。"""
    SECONDARY_TEXT = "secondary_text"
    CLEANED_TEXT = "cleaned_text"
    LAYOUT_JSON = "layout_json"
    EXTRACTED_TABLE = "extracted_table"
    EXTRACTED_IMAGE = "extracted_image"
