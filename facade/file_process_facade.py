from typing import  List
from processors.processor_factory import ProcessorFactory
from core.logger import logger
from utils.StructureDetector import detector
from utils.hierarchical_chunker import chunker
# 新增：混合存储库
from core.vector_store import vector_store

class FileProcessFacade:
    _instance = None

    def __new__(cls):
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls)
        return cls._instance

    def process_file(self, file_path: str) -> str|None:
        logger.info(f"门面入口开始处理文件: {file_path}")
        processor = ProcessorFactory.get_processor(file_path)
        if not processor:
            logger.error(f"不支持的文件类型: {file_path}")
            return None
        saved_path = processor.process(file_path)
        if saved_path:
            logger.info(f"文件处理完成: {saved_path}")
        else:
           logger.error(f"文件处理失败: {file_path}")
        return saved_path

    def process_and_split(self, file_path: str) -> List[dict]:
        logger.info(f"🚀 全流程处理：文件→清洗→分块→父子分块 | {file_path}")
        saved_path = self.process_file(file_path)
        if not saved_path:
            return []
        try:
            with open(saved_path, "r", encoding="utf-8") as f:
                clean_content = f.read()
        except Exception as e:
            logger.error(f"读取文件失败: {e}")
            return []
        structure_blocks = detector.extract_markdown_structure(clean_content)
        hierarchical_blocks = chunker.build_chunks(structure_blocks)
        logger.info(f"✅ 处理完成，生成 {len(hierarchical_blocks)} 个父子分块")
        return hierarchical_blocks

    # ======================
    # 🔥 新增：一键处理 + 入库
    # ======================
    def process_and_store(self, file_path: str) -> bool:
        """文件 → 处理 → 分块 → 向量入库（全自动化）"""
        chunks = self.process_and_split(file_path)
        if not chunks:
            return False
        vector_store.add_hierarchical_chunks(file_path, chunks)
        return True

    # ======================
    # 🔥 新增：自然语言检索
    # ======================
    def query(self, question: str, top_k: int = 5):
        """混合检索，返回父块结果"""
        return vector_store.hybrid_search(question, top_k)

file_facade = FileProcessFacade()