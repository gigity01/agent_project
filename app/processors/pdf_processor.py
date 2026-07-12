"""PDF 处理器预留实现，计划通过 Docling 转换为 Markdown。"""

from pathlib import Path

from app.processors.base import BaseProcessor, ProcessResult
from integrations.document_converter.docling_client import DoclingClient

from app_config.settings import DOCLING_OUTPUT_TYPE

class PdfProcessor(BaseProcessor):
      """PDF 到 Markdown 的外部转换处理器占位定义。"""

      source_type = "pdf"

      def __init__(self):
          """初始化外部文档转换客户端。"""
          self.docling_client = DoclingClient(
              base_url=DOCLING_OUTPUT_TYPE

          )

      def process(self, source_path: Path, cleaned_path: Path) -> ProcessResult:
          """处理入口预留，待补充 PDF 转换与落盘逻辑。"""



