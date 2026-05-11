from typing import Optional
from langchain_community.document_loaders import UnstructuredMarkdownLoader

from processors.base_processor import BaseFileProcessor
from utils.file_utils import is_safe_file_path, save_cleaned_file
from utils.text_utils import clean_text, deduplicate_lines
from core.logger import logger
from core.singleton import singleton






class MdProcessor(BaseFileProcessor):
    MDHolder_cls = UnstructuredMarkdownLoader

    def read(self, file_path: str) -> Optional[str]:
        try:
            loader = self.MDHolder_cls(file_path)
            docs = loader.load()
            full_text = "\n".join([d.page_content for d in docs])
            return full_text
        except Exception as e:
            logger.error(f"MD解析失败: {file_path}", exc_info=True)
            return None

    def process(self, file_path: str) -> Optional[str]:
        if not is_safe_file_path(file_path):
            return None

        raw_text = self.read(file_path)
        if not raw_text:
            return None

        clean_txt = clean_text(raw_text)
        final_txt = deduplicate_lines(clean_txt)

        suffix = ".md"
        saved_path = save_cleaned_file(final_txt, suffix)
        logger.info(f"MD处理完成 源文件:{file_path} 处理后:{saved_path}")
        return saved_path