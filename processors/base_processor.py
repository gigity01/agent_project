from abc import ABC, abstractmethod
from typing import Optional

class BaseFileProcessor(ABC):
    """文件处理器基类"""

    @abstractmethod
    def read(self, file_path: str) -> str|None:
        """读取文件原始内容"""
        pass

    @abstractmethod
    def process(self, file_path: str) -> str|None:
        """完整处理：读取->清洗->去重->保存，返回清洗后文件路径"""
        pass