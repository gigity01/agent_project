"""供 Planner 和 Catalog 读取的 Tool 能力描述。"""

from typing import Literal

from pydantic import BaseModel, Field


class ToolDescriptor(BaseModel):
    """不依赖 Python 函数源码的稳定 Tool 元数据描述模型。

    用于动态向 Planner、GapHandler 及 Catalog 暴露工具能力元信息：
    - name: 工具唯一标识符。
    - description: 工具功能中文描述。
    - operation_type: 操作类型（query 只读查询、command 状态修改命令、workflow 复杂工作流）。
    - side_effect: 是否具有外部持久化副作用。
    - idempotency: 幂等语义（read_only、state_guarded、idempotent、non_idempotent）。
    - required_permissions: 执行此工具所需的权限集合。
    - resource_types: 此工具涉及的业务资源类型（如 document、context_chain 等）。
    - approval_required: 是否需要人工二次确认授权。
    """

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
