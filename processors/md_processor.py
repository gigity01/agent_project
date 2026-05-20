
from langchain_community.document_loaders import UnstructuredMarkdownLoader
from processors.base_processor import BaseFileProcessor
from utils.file_utils import is_safe_file_path, save_cleaned_file
from utils.text_utils import clean_text, deduplicate_lines
from utils.text_normalizer import normalizer  # 统一标准化
from core.logger import logger
from config.settings import MAX_READ_SIZE


class MdProcessor(BaseFileProcessor):

    MDHolder_cls = UnstructuredMarkdownLoader


    def read(self, file_path: str) -> str|None:
        try:
            loader = self.MDHolder_cls(file_path)
            docs = loader.load()
            full_text = "\n".join([d.page_content for d in docs])
            if len(full_text) > MAX_READ_SIZE:
                full_text = full_text[:MAX_READ_SIZE]
                logger.warning(f"MD截断: {file_path}")
            return full_text
        except Exception as e:
            logger.error(f"MD解析失败: {file_path}", exc_info=True)
            return None

    def process(self, file_path: str) -> str|None:
        # 统一流程：全部返回 TXT 路径
        if not is_safe_file_path(file_path):
            return None

        raw_text = self.read(file_path)
        if not raw_text:
            return None

        # 统一标准化
        norm_text = normalizer.clean(raw_text)
        clean_txt = clean_text(norm_text)
        final_txt = deduplicate_lines(clean_txt)

        # 统一保存为 TXT
        saved_path = save_cleaned_file(final_txt, origin_suffix=".txt")
        logger.info(f"MD处理完成: {saved_path}")

        return saved_path