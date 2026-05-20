
from langchain_community.document_loaders import PyPDFLoader

from processors.base_processor import BaseFileProcessor
from utils.file_utils import is_safe_file_path, save_cleaned_file
from utils.text_utils import clean_text, deduplicate_lines
from core.logger import logger
from utils.text_normalizer import normalizer

"""
    pdf文件会使用marker处理为md文件，再使用md文件的处理策略
    这里的pdf处理只是简单处理，本项目中不会如此处理pdf文件
    
"""




class PdfProcessor(BaseFileProcessor):
    loader_cls = PyPDFLoader

    def read(self, file_path: str) -> str|None:
        try:
            loader = self.loader_cls(file_path)
            pages = loader.load()
            full_text = "\n".join([p.page_content for p in pages])
            return full_text
        except Exception as e:
            logger.error(f"PDF解析失败: {file_path}", exc_info=True)
            return None

    def process(self, file_path: str) ->str|None:
        if not is_safe_file_path(file_path):
            return None

        raw_text = self.read(file_path)
        if not raw_text:
            return None

        normalized_text = normalizer.clean(raw_text)
        clean_txt = clean_text(normalized_text)
        final_txt = deduplicate_lines(clean_txt)

        suffix = ".txt"
        saved_path = save_cleaned_file(final_txt, suffix)
        logger.info(f"PDF处理完成 源文件:{file_path} 处理后:{saved_path}")
        return saved_path