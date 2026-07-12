
"""文档转换服务返回 Markdown 的通用数据模型。"""

from pathlib import Path
from typing import Any
from pydantic import Field, BaseModel ,ConfigDict



class MarkdownConvertResult(BaseModel):
    """外部转换后的 Markdown 内容与转换元数据。"""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    source_path: Path
    source_format: str
    markdown: str
    provider: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
