"""文档源类型判定、格式归一化与内容哈希策略。

定义系统支持的本地格式、外部 Docling 转换格式，以及处理输出格式判定逻辑。
"""

import hashlib

# 支持直接本地清洗转换的格式（纯文本、Markdown、CSV 数据表）
LOCAL_PROCESS_SOURCE_TYPES = {"txt", "md", "csv"}

# 必须依赖外部转换服务（如 Docling）先转换为 Markdown 的复杂办公格式
EXTERNAL_PROCESS_SOURCE_TYPES = {"pdf", "ppt", "pptx", "doc", "docx"}

# 扩展名同义词/别名归一化字典
SOURCE_TYPE_ALIASES = {"markdown": "md"}


def md5_text(text: str) -> str:
    """计算文本正文的 MD5 哈希值。

    常用于父级语义块正文哈希（content_hash）计算，以在切块与重建时快速识别内容变动。

    Args:
        text: 待哈希的输入纯文本字符串。

    Returns:
        32 位小写十六进制 MD5 散列值字符串。
    """
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def normalize_source_type(source_type: str) -> str:
    """归一化文档源类型/扩展名字符串。

    去除前导点号、首尾空白，转换为小写，并将 'markdown' 等别名统一映射为标准扩展名（如 'md'）。

    Args:
        source_type: 输入的原始文件扩展名或类型字符串（如 '.Markdown', 'PDF', 'md'）。

    Returns:
        归一化后的标准类型字符串（如 'md', 'pdf'）。
    """
    normalized_source_type = source_type.lower().strip().lstrip(".")
    return SOURCE_TYPE_ALIASES.get(normalized_source_type, normalized_source_type)


def requires_external_processing(source_type: str) -> bool:
    """判定给定源文件格式是否必须通过外部服务（如 Docling）转换为 Markdown。

    根据 AGENTS.md 规范：
    - 本地格式：txt, md, csv -> 不需要外部转换（返回 False）
    - 外部格式：pdf, doc, docx, ppt, pptx -> 需要外部转换（返回 True）

    Args:
        source_type: 文件扩展名或源类型标识。

    Returns:
        若需要外部转换服务则返回 True，否则返回 False。
    """
    return normalize_source_type(source_type) in EXTERNAL_PROCESS_SOURCE_TYPES


def get_expected_process_output_type(source_type: str) -> str:
    """获取文档在 Process 处理阶段完成后预期的标准化输出格式。

    复杂办公格式（PDF/DOCX/PPTX 等）经 Docling 处理后统一输出 Markdown ('md')，
    本地格式（txt, md, csv）在清洗后保持自身标准格式。

    Args:
        source_type: 原始输入文件类型或扩展名。

    Returns:
        预期产物标准类型（如 'md', 'txt', 'csv'）。
    """
    normalized_source_type = normalize_source_type(source_type)
    if requires_external_processing(normalized_source_type):
        # 外部复杂格式转换后统一以 markdown (.md) 产出
        return "md"
    return normalized_source_type
