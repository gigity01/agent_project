from pathlib import Path

from integrations.document_converter.docling_client import DoclingClient
from processors.base import BaseProcessor, ProcessResult


class ExternalMarkdownProcessor(BaseProcessor):

    def __init__(self, source_type: str, client: DoclingClient) -> None:
        self.source_type = source_type
        self.client = client




    def process(self, source_path: Path, cleaned_path: Path) -> ProcessResult:


