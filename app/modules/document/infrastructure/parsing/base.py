"""文档模块原始文件清洗处理器的统一契约与结果模型。"""

from abc import ABC, abstractmethod
from pathlib import Path

from app.modules.document.domain.models import ProcessResult


class BaseProcessor(ABC):
    """
    文件处理器基类。
    raw file -> cleaned file
    """

    source_type: str

    @abstractmethod
    def process(
        self,
        source_path: Path,
        cleaned_path: Path,
    ) -> ProcessResult:
        """读取源文件、生成清洗文件，并返回处理结果。"""
        raise NotImplementedError

    def validate_source_path(self, source_path: Path) -> Path:
        """确认源路径存在且为普通文件后返回绝对路径。"""
        if not source_path.exists():
            raise FileNotFoundError(f"源文件不存在: {source_path}")

        if not source_path.is_file():
            raise ValueError(f"源路径不是有效文件: {source_path}")
        return source_path.resolve()


    def prepare_cleaned_path(self, cleaned_path: Path) -> Path:
        """创建输出父目录，并拒绝将目录作为输出文件。"""
        if cleaned_path.exists() and cleaned_path.is_dir():
            raise ValueError(f"清洗输出路径不能是目录: {cleaned_path}")

        cleaned_path.parent.mkdir(parents=True, exist_ok=True)
        return cleaned_path.resolve()
