"""文档工作流与阶段操作的日志全链路关联上下文模型模块。

职责说明：
- 定义不可变数据类 `DocumentOperationContext`，封装一次文档流水线执行的唯一关联标识（`workflow_id`、`operation_id`、`attempt`、`parent_operation_id`）。
- 确保从 Upload、Process、Chunk 到 Index 的所有结构化日志事件与 Task Runtime 的执行记录保持关联可追溯。
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True)
class DocumentOperationContext:
    """文档单阶段执行的不可变全链路追踪关联上下文。

    属性:
        workflow_id: 顶层文档工作流/任务批次唯一标识。
        operation_id: 当前单次阶段操作唯一标识（也是 Document 的 ownership token 与补偿边界）。
        attempt: 当前操作的重试尝试序号（从 1 开始）。
        parent_operation_id: 可选的父操作或前序尝试操作标识。
    """

    workflow_id: str
    operation_id: str
    attempt: int
    parent_operation_id: str | None = None

    def __post_init__(self) -> None:
        """校验必填字段非空及重试序号合法性。"""
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
        parent_operation_id: str | None = None,
    ) -> "DocumentOperationContext":
        """工厂方法：创建关联上下文，并在调用方未提供 ID 时自动生成全局唯一 UUID。

        参数:
            workflow_id: 工作流标识（缺省时自动生成）。
            operation_id: 操作标识（缺省时自动生成）。
            attempt: 重试序号（默认 1）。
            parent_operation_id: 父级操作标识。

        返回:
            DocumentOperationContext: 关联上下文实例。
        """
        return cls(
            workflow_id=workflow_id or uuid4().hex,
            operation_id=operation_id or uuid4().hex,
            attempt=attempt,
            parent_operation_id=parent_operation_id,
        )
