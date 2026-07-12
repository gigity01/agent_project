"""Markdown 转换服务返回结果的数据模型。"""

from pathlib import Path
from pydantic import BaseModel,ConfigDict,Field
from typing import Any
class MarkdownConvertResult(BaseModel):
    """描述源文件被转换为 Markdown 后的内容、状态和元数据。"""
    model_config= ConfigDict(arbitrary_types_allowed=True)
    source_path: Path
    source_format: str
    markdown: str
    provider: str
    status: str
    metadata: dict[str, Any]=Field(default_factory=dict)

