"""Planning Use Case 的显式输入与输出。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.planning.domain.enums import PlanStatus


class _PlanningInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreatePlanInput(_PlanningInput):
    turn_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(default=1, ge=1)


class _CreateDocumentTaskInput(_PlanningInput):
    plan_id: str = Field(min_length=1, max_length=100)
    turn_id: str = Field(min_length=1, max_length=100)
    document_id: int = Field(gt=0)
    sequence: int = Field(ge=1)


class CreateProcessDocumentTaskInput(_CreateDocumentTaskInput):
    """创建文档处理 Task 的输入。"""


class CreateBuildChunksTaskInput(_CreateDocumentTaskInput):
    """创建文档切块 Task 的输入。"""


class CreateIndexVectorsTaskInput(_CreateDocumentTaskInput):
    """创建文档索引 Task 的输入。"""


class FinalizePlanInput(_PlanningInput):
    plan_id: str = Field(min_length=1, max_length=100)
    turn_id: str = Field(min_length=1, max_length=100)


class MarkPlanUnsupportedInput(_PlanningInput):
    plan_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=4000)


class MarkPlanRetryPendingInput(_PlanningInput):
    plan_id: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=4000)


class PlanResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: str
    turn_id: str
    status: str
    revision: int
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class TaskResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    plan_id: str
    turn_id: str
    capability_code: str
    input_json: dict
    sequence: int
    status: str
    created_at: datetime
    updated_at: datetime


class FinalizePlanResult(BaseModel):
    plan_id: str
    turn_id: str
    plan_status: str
    task_ids: list[str]


class RunPlanningInput(_PlanningInput):
    conversation_id: str = Field(min_length=1, max_length=100)
    turn_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(default=1, ge=1)


class RunPlanningResult(BaseModel):
    plan_id: str
    turn_id: str
    status: PlanStatus
    task_ids: list[str]
    failure_reason: str | None
