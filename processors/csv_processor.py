from typing import Optional
import pandas as pd
from processors.base_processor import BaseFileProcessor
from utils.file_utils import is_safe_file_path, save_cleaned_file
from utils.text_utils import clean_text, deduplicate_lines
from core.logger import logger


class CsvProcessor(BaseFileProcessor):
    # 分块大小：每批读100行，可根据文件大小调整（生产推荐 100~500）
    CHUNK_SIZE = 100

    def read(self, file_path: str) -> Optional[str]:
        """
        【生产级】分块读取CSV + 语义化转换
        优点：低内存、支持超大CSV、不爆内存
        """
        try:
            # ==========================================
            # 关键：分块读取 CSV（迭代器，不加载全量数据）
            # ==========================================
            chunk_iter = pd.read_csv(
                file_path,
                low_memory=True,
                chunksize=self.CHUNK_SIZE,  # 分块核心
                encoding_errors="ignore"  # 兼容乱码
            )
            semantic_lines = []
            row_index = 0

            # 迭代处理每一个块
            for chunk in chunk_iter:
                # 去除空行/空值
                chunk = chunk.dropna(how="all")
                columns = chunk.columns.tolist()

                # 逐行语义化转换
                for _, row in chunk.iterrows():
                    row_index += 1
                    row_content = []
                    for col in columns:
                        value = str(row[col]).strip() if pd.notna(row[col]) else "无"
                        row_content.append(f"{col}：{value}")

                    # 生成带序号的语义行（对齐MD层级结构）
                    semantic_line = f"【第{row_index}条数据】{'，'.join(row_content)}。"
                    semantic_lines.append(semantic_line)

            # 用空行分隔，符合标准化规则
            return "\n\n".join(semantic_lines)

        except Exception as e:
            logger.error(f"CSV分块读取失败: {file_path}", exc_info=True)
            return None

    def process(self, file_path: str) -> Optional[str]:
        # ======================
        # 你原有逻辑 完全不动
        # ======================
        if not is_safe_file_path(file_path):
            return None

        # 分块读取 + 语义化
        raw_text = self.read(file_path)
        if not raw_text:
            return None

        # 清洗 + 去重
        clean_txt = clean_text(raw_text)
        final_txt = deduplicate_lines(clean_txt)

        # 保存结果
        suffix = ".csv"
        saved_path = save_cleaned_file(final_txt, suffix)
        logger.info(f"✅ CSV处理完成 | 源文件:{file_path} | 输出:{saved_path}")
        return saved_path