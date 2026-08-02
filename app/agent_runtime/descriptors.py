"""供 Planner 和 Catalog 读取的 Tool 能力描述。"""

from typing import Literal

from pydantic import BaseModel, Field


class ToolDescriptor(BaseModel):
    """不依赖 Python 函数源码的稳定 Tool 元数据。"""

    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    operation_type: Literal["query", "command", "workflow"]
    side_effect: bool
    idempotency: Literal[
        "read_only",
        "state_guarded",
        "idempotent",
        "non_idempotent",
    ]
    required_permissions: list[str]
    resource_types: list[str]
    approval_required: bool
