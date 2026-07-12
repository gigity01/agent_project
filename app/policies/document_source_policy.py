"""文档源类型的别名归一化和处理路径判定规则。"""

LOCAL_PROCESS_SOURCE_TYPES = {"txt", "md", "csv"}

EXTERNAL_PROCESS_SOURCE_TYPES = {"pdf", "ppt", "pptx", "doc", "docx"}


SOURCE_TYPE_ALIASES = {
    "markdown": "md",
}


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
