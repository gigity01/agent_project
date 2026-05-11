from typing import Optional
from processors.processor_factory import ProcessorFactory
from core.logger import logger


class FileProcessFacade:

    def __new__(cls):
        # 全局唯一入口
        if not hasattr(cls, "_instance"):
            cls._instance = super().__new__(cls)
        return cls._instance

    def process_file(self, file_path: str) -> Optional[str]:
        """
        统一入口：传入本地文件路径，自动完成全流程
        安全校验 -> 匹配处理器 -> 读取 -> 清洗 -> 去重 -> 保存
        返回：清洗后文件绝对路径 / 失败返回None
        """
        logger.info(f"门面入口开始处理文件: {file_path}")

        # 1. 工厂获取对应处理器（自带实例缓存）
        processor = ProcessorFactory.get_processor(file_path)
        if not processor:
            logger.error(f"不支持的文件类型或获取处理器失败: {file_path}")
            return None

        # 2. 调用处理器完整流程
        saved_path = processor.process(file_path)
        if saved_path:
            logger.info(f"门面入口处理完成，清洗文件路径: {saved_path}")
        else:
            logger.error(f"门面入口处理失败: {file_path}")

        return saved_path

    def process_and_split(self, file_path: str) -> list[str]:
        """
        完整流程：处理文件 → 清洗 → 去重 → 分块
        返回：分块后的文本列表
        """
        logger.info(f"🚀 门面入口：处理 + 分块 文件: {file_path}")

        # 1. 处理文件（清洗+保存）
        saved_path = self.process_file(file_path)
        if not saved_path:
            return []

        # 2. 读取清洗后的干净文本
        try:
            with open(saved_path, "r", encoding="utf-8") as f:
                clean_content = f.read()
        except:
            logger.error("读取清洗后文件失败")
            return []

        # 3. 单例分块
        from utils.splitter_utils import text_splitter
        chunks = text_splitter.split_text(clean_content)

        logger.info(f"✅ 全流程完成：文件→清洗→分块，共 {len(chunks)} 块")
        return chunks



file_facade = FileProcessFacade()