import os
from typing import  Type
from processors.base_processor import BaseFileProcessor
from processors.md_processor import MdProcessor
from processors.pdf_processor import PdfProcessor
from processors.txt_processor import TxtProcessor
from processors.csv_processor import CsvProcessor


class ProcessorFactory:
    _instance_cache: dict[Type[BaseFileProcessor], BaseFileProcessor] = {}

    @staticmethod
    def get_processor(file_path: str) -> BaseFileProcessor|None:
        """根据文件后缀，获取对应处理器单例实例"""
        ext = os.path.splitext(file_path)[-1].lower()

        processor_map: dict[str, Type[BaseFileProcessor]] = {
            ".txt": TxtProcessor,
            ".csv": CsvProcessor,
            ".md": MdProcessor,
            ".pdf": PdfProcessor,
        }

        if ext not in processor_map:
            return None

        cls = processor_map[ext]

        # 单例缓存：只创建一次，全局复用
        if cls not in ProcessorFactory._instance_cache:
            ProcessorFactory._instance_cache[cls] = cls()

        return ProcessorFactory._instance_cache[cls]