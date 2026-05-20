

from config.settings import MAX_READ_SIZE
from processors.base_processor import BaseFileProcessor
from utils.file_utils import is_safe_file_path, save_cleaned_file
from utils.text_utils import clean_text, deduplicate_lines
from utils.text_normalizer import normalizer  # 统一标准化
from core.logger import logger


class TxtProcessor(BaseFileProcessor):
    


    def read(self, file_path: str) -> str|None:
        encodings = ["utf-8", "gbk", "gb2312"]
        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    text = f.read()
                if len(text) > MAX_READ_SIZE:
                    text = text[:MAX_READ_SIZE]
                    logger.warning(f"TXT截断: {file_path}")
                return text
            except UnicodeDecodeError:
                continue
        logger.error(f"TXT编码失败: {file_path}")
        return None

    def process(self, file_path: str) -> str|None:
        if not is_safe_file_path(file_path):
            return None

        raw_text = self.read(file_path)
        if not raw_text:
            return None

        # 统一标准化流程
        norm_text = normalizer.clean(raw_text)
        clean_txt = clean_text(norm_text)
        final_txt = deduplicate_lines(clean_txt)

        # 全部保存为 TXT
        saved_path = save_cleaned_file(final_txt, origin_suffix=".txt")
        logger.info(f"TXT处理完成: {saved_path}")
        return saved_path