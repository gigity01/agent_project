
from pathlib import Path
from typing import Any
from pydantic import Field, BaseModel ,ConfigDict



class MarkdownConvertResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    source_path: Path
    source_format: str
    markdown: str
    provider: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)