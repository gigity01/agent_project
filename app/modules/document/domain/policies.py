"""文档源类型与内容哈希业务规则。"""

import hashlib

LOCAL_PROCESS_SOURCE_TYPES = {"txt", "md", "csv"}
EXTERNAL_PROCESS_SOURCE_TYPES = {"pdf", "ppt", "pptx", "doc", "docx"}
SOURCE_TYPE_ALIASES = {"markdown": "md"}


def md5_text(text: str) -> str:
    """计算父块正文哈希，用于重建时识别内容。"""

    return hashlib.md5(text.encode("utf-8")).hexdigest()


def normalize_source_type(source_type: str) -> str:
    """统一扩展名大小写、前导点和别名。"""

    normalized_source_type = source_type.lower().strip().lstrip(".")
    return SOURCE_TYPE_ALIASES.get(normalized_source_type, normalized_source_type)


def requires_external_processing(source_type: str) -> bool:
    """判断文件是否必须先通过外部转换服务处理。"""

    return normalize_source_type(source_type) in EXTERNAL_PROCESS_SOURCE_TYPES


def get_expected_process_output_type(source_type: str) -> str:
    """返回处理步骤应产生的标准化输出格式。"""

    normalized_source_type = normalize_source_type(source_type)
    if requires_external_processing(normalized_source_type):
        return "md"
    return normalized_source_type
