from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MarkdownConvertResult:
    source_path: Path
    source_format: str
    markdown: str
    provider: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)