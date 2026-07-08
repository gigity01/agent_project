# app/processors/base.py

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from pydantic import BaseModel,ConfigDict,Field


class ProcessResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    source_path: Path
    cleaned_path: Path
    source_type: str
    char_count: int = 0
    line_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


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
        raise NotImplementedError

    def validate_source_path(self, source_path: Path) -> Path:
        if not source_path.exists():
            raise FileNotFoundError(f"源文件不存在: {source_path}")

        if not source_path.is_file():
            raise ValueError(f"源路径不是有效文件: {source_path}")
        return source_path.resolve()


    def prepare_cleaned_path(self, cleaned_path: Path) -> Path:
        if cleaned_path.exists() and cleaned_path.is_dir():
            raise ValueError(f"清洗输出路径不能是目录: {cleaned_path}")

        cleaned_path.parent.mkdir(parents=True, exist_ok=True)
        return cleaned_path.resolve()