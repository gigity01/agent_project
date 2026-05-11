from typing import Optional
from processors.base_processor import BaseFileProcessor
from utils.file_utils import is_safe_file_path, save_cleaned_file
from utils.text_utils import clean_text, deduplicate_lines
from core.logger import logger


class TxtProcessor(BaseFileProcessor):
    def read(self, file_path: str) -> Optional[str]:
        """读取TXT，兼容多编码"""
        encodings = ["utf-8", "gbk", "gb2312"]
        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        logger.error(f"TXT编码全部解析失败: {file_path}")
        return None

    def process(self, file_path: str) -> Optional[str]:
        # 1. 安全校验
        if not is_safe_file_path(file_path):
            return None

        # 2. 读取原始文本
        raw_text = self.read(file_path)
        if not raw_text:
            return None

        # 3. 清洗 + 按行去重
        clean_txt = clean_text(raw_text)
        final_txt = deduplicate_lines(clean_txt)

        # 4. 保存清洗后文件
        suffix = file_path.lower()[-4:]
        saved_path = save_cleaned_file(final_txt, suffix)
        logger.info(f"TXT处理完成 源文件:{file_path} 处理后:{saved_path}")
        return saved_path