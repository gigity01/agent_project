"""Planner Tools 的 SDK 输入输出 Schema。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateProcessDocumentTaskToolInput(_ToolInput):
    task_ref: str = Field(min_length=1, max_length=100)
    document_id: int = Field(gt=0)
    sequence: int = Field(ge=1)
    depends_on_task_refs: list[str] = Field(default_factory=list, max_length=10)


class CreateBuildChunksTaskToolInput(_ToolInput):
    task_ref: str = Field(min_length=1, max_length=100)
    document_id: int = Field(gt=0)
    sequence: int = Field(ge=1)
    depends_on_task_refs: list[str] = Field(default_factory=list, max_length=10)


class CreateIndexVectorsTaskToolInput(_ToolInput):
    task_ref: str = Field(min_length=1, max_length=100)
    document_id: int = Field(gt=0)
    sequence: int = Field(ge=1)
    depends_on_task_refs: list[str] = Field(default_factory=list, max_length=10)


class FinalizePlanToolInput(_ToolInput):
    """Finalize 不接收模型提供的 Plan/Turn 标识。"""


class MarkPlanUnsupportedToolInput(_ToolInput):
    reason: str = Field(min_length=1, max_length=4000)


class PlanningToolOutput(BaseModel):
    outcome: Literal["succeeded", "rejected", "failed"]
    result_code: str
    message: str
    retryable: bool
    resource_refs: list[str]
    plan_id: str | None = None
    task_id: str | None = None
    status: str | None = None
    task_ids: list[str] = Field(default_factory=list)
