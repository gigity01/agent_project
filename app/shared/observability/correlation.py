"""文档工作流与阶段操作的日志关联上下文。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class DocumentOperationContext:
    """一次文档阶段执行使用的稳定关联标识。"""

    workflow_id: str
    operation_id: str
    attempt: int
    parent_operation_id: None = None

    def __post_init__(self) -> None:
        if not self.workflow_id.strip():
            raise ValueError("workflow_id 不能为空")
        if not self.operation_id.strip():
            raise ValueError("operation_id 不能为空")
        if self.attempt < 1:
            raise ValueError("attempt 必须大于等于 1")

    @classmethod
    def create(
        cls,
        *,
        workflow_id: str | None = None,
        operation_id: str | None = None,
        attempt: int = 1,
    ) -> "DocumentOperationContext":
        """补齐缺省 ID；每次调用默认生成新的 operation_id。"""
        return cls(
            workflow_id=workflow_id or uuid4().hex,
            operation_id=operation_id or uuid4().hex,
            attempt=attempt,
        )
