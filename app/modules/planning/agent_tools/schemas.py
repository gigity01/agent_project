"""Planner Tools 的 Agents SDK 输入输出 Schema 定义。

提供各个 Planning Tool 调用的参数验证模型（Pydantic），
确保 OpenAI Agents SDK / Function Calling 输入输出与领域模型严格匹配。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ToolInput(BaseModel):
    """所有 Planning Tool 输入参数的基类，禁止额外未声明字段。"""

    model_config = ConfigDict(extra="forbid")


class CreateProcessDocumentTaskToolInput(_ToolInput):
    """创建文档处理（Process Document）任务的工具输入参数。"""

    task_ref: str = Field(
        min_length=1,
        max_length=100,
        description="Plan 内任务的唯一局部引用标识（如 task_1）",
    )
    document_id: int = Field(gt=0, description="目标文档的全局唯一数字 ID")
    sequence: int = Field(ge=1, description="Plan 内任务执行序号，从 1 开始严格递增")
    depends_on_task_refs: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="当前任务依赖的前置任务 task_ref 列表",
    )


class CreateBuildChunksTaskToolInput(_ToolInput):
    """创建文档切块（Build Document Chunks）任务的工具输入参数。"""

    task_ref: str = Field(
        min_length=1,
        max_length=100,
        description="Plan 内任务的唯一局部引用标识（如 task_2）",
    )
    document_id: int = Field(gt=0, description="目标文档的全局唯一数字 ID")
    sequence: int = Field(ge=1, description="Plan 内任务执行序号，从 1 开始严格递增")
    depends_on_task_refs: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="当前任务依赖的前置任务 task_ref 列表",
    )


class CreateIndexVectorsTaskToolInput(_ToolInput):
    """创建文档向量索引（Index Document Vectors）任务的工具输入参数。"""

    task_ref: str = Field(
        min_length=1,
        max_length=100,
        description="Plan 内任务的唯一局部引用标识（如 task_3）",
    )
    document_id: int = Field(gt=0, description="目标文档的全局唯一数字 ID")
    sequence: int = Field(ge=1, description="Plan 内任务执行序号，从 1 开始严格递增")
    depends_on_task_refs: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="当前任务依赖的前置任务 task_ref 列表",
    )


class FinalizePlanToolInput(_ToolInput):
    """发布并确认 Plan 的工具输入参数。

    Finalize 不接收模型提供的 Plan/Turn 标识，强制从运行时上下文中安全提取。
    """


class MarkPlanUnsupportedToolInput(_ToolInput):
    """将 Plan 标记为不支持（Unsupported）的工具输入参数。"""

    reason: str = Field(
        min_length=1,
        max_length=4000,
        description="不支持当前用户请求的详细原因说明",
    )


class PlanningToolOutput(BaseModel):
    """Planning Tools 执行后的标准结构化输出契约。"""

    outcome: Literal["succeeded", "rejected", "failed"] = Field(
        description="工具执行结果分类：成功、业务拒绝或系统失败"
    )
    result_code: str = Field(description="稳定的机器可读结果码")
    message: str = Field(description="面向人类的可读结果或错误提示")
    retryable: bool = Field(description="失败是否可通过重试恢复")
    resource_refs: list[str] = Field(
        default_factory=list,
        description="本次工具操作涉及或产生的资源引用列表（如 plan:xxx, task:yyy）",
    )
    plan_id: str | None = Field(default=None, description="操作关联的 Plan ID")
    task_id: str | None = Field(default=None, description="创建的 Task ID（若适用）")
    status: str | None = Field(default=None, description="Plan 或 Task 的当前最新状态")
    task_ids: list[str] = Field(
        default_factory=list,
        description="Plan 发布后包含的全部 Task ID 列表（若适用）",
    )
