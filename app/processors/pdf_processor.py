from pathlib import Path

from app.processors.base import BaseProcessor, ProcessResult
from integrations.document_converter.docling_client import DoclingClient

from app_config.settings import DOCLING_OUTPUT_TYPE

class PdfProcessor(BaseProcessor):

      source_type = "pdf"

      def __init__(self):
          self.docling_client = DoclingClient(
              base_url=DOCLING_OUTPUT_TYPE

          )

      def process(self, source_path: Path, cleaned_path: Path) -> ProcessResult:



