
import pandas as pd
from processors.base_processor import BaseFileProcessor
from utils.file_utils import is_safe_file_path, save_cleaned_file
from utils.text_utils import clean_text, deduplicate_lines
from utils.text_normalizer import normalizer  # 统一标准化
from core.logger import logger
from config.settings import CHILD_CHUNK_MAX_LEN

class CsvProcessor(BaseFileProcessor):

    MAX_READ_SIZE = 1024 * 1024

    def read(self, file_path: str) -> str|None:
        try:
            chunk_iter = pd.read_csv(
                file_path,
                low_memory=True,
                chunksize=CHILD_CHUNK_MAX_LEN,
                encoding_errors="ignore"
            )
            lines = []
            idx = 0
            for chunk in chunk_iter:
                chunk = chunk.dropna(how="all")
                cols = chunk.columns.tolist()
                for _, row in chunk.iterrows():
                    idx += 1
                    items = [f"{c}：{str(row[c]) if pd.notna(row[c]) else '无'}" for c in cols]
                    lines.append(f"【第{idx}条】{'，'.join(items)}。")
            text = "\n\n".join(lines)
            if len(text) > self.MAX_READ_SIZE:
                text = text[:self.MAX_READ_SIZE]
                logger.warning(f"CSV截断: {file_path}")
            return text
        except Exception as e:
            logger.error(f"CSV读取失败: {file_path}", exc_info=True)
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
        logger.info(f"CSV处理完成: {saved_path}")
        return saved_path