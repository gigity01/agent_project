"""使用外部服务将复杂文档转换为 Markdown 的处理器占位定义。"""

from pathlib import Path

from integrations.document_converter.docling_client import DoclingClient
from processors.base import BaseProcessor, ProcessResult


class ExternalMarkdownProcessor(BaseProcessor):
    """委托文档转换客户端处理 PDF、Office 等外部格式。"""

    def __init__(self, source_type: str, client: DoclingClient) -> None:
        """保存源类型与已注入的外部转换客户端。"""
        self.source_type = source_type
        self.client = client




    def process(self, source_path: Path, cleaned_path: Path) -> ProcessResult:
        """处理入口预留，待补充转换结果的保存与统计逻辑。"""


