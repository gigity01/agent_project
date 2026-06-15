# app/processors/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProcessResult:
    source_path: Path
    cleaned_path: Path
    source_type: str
    char_count: int = 0
    line_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


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

    def validate_source_path(self, source_path: Path) -> None:
        if not source_path.exists():
            raise FileNotFoundError(f"源文件不存在: {source_path}")

        if not source_path.is_file():
            raise ValueError(f"源路径不是有效文件: {source_path}")