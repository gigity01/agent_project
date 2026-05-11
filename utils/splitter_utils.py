# 正确导入方式（新版）
from langchain_text_splitters import RecursiveCharacterTextSplitter
from core.singleton import singleton
from core.logger import logger

# 分块配置（可根据模型调整）
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 100

# 单例：全局只创建 1 个分块器
@singleton
class TextSplitter:
    def __init__(self):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", " ", ""],
        )
        logger.info("✅ 文本分块器初始化完成（全局单例）")

    def split_text(self, text: str) -> list[str]:
        if not text:
            return []
        chunks = self.splitter.split_text(text)
        logger.info(f"📦 文本分块完成，共 {len(chunks)} 块")
        return chunks

# 全局唯一分块实例
text_splitter = TextSplitter()