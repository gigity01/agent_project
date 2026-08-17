"""Planning Use Case 的显式输入与输出。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.context.domain.models import ContextChain
from app.modules.planning.domain.enums import PlanStatus


class _PlanningInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreatePlanInput(_PlanningInput):
    turn_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(default=1, ge=1)
    workflow_id: str | None = Field(default=None, min_length=1, max_length=100)
    parent_plan_id: str | None = Field(default=None, min_length=1, max_length=100)


class _CreateDocumentTaskInput(_PlanningInput):
    plan_id: str = Field(min_length=1, max_length=100)
    turn_id: str = Field(min_length=1, max_length=100)
    document_id: int = Field(gt=0)
    sequence: int = Field(ge=1)
    task_ref: str = Field(min_length=1, max_length=100)
    depends_on_task_refs: list[str] = Field(default_factory=list, max_length=10)


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


class MarkPlanNeedsClarificationInput(_PlanningInput):
    plan_id: str = Field(min_length=1, max_length=100)
    conversation_id: str = Field(min_length=1, max_length=100)
    kind: str = Field(pattern=r"^(resource|intent|missing_parameter)$")
    reason: str = Field(min_length=1, max_length=4000)
    required_information: list[str] = Field(min_length=1, max_length=10)
    known_resource_refs: list[str] = Field(default_factory=list, max_length=50)


class SetClarificationQuestionInput(_PlanningInput):
    plan_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=4000)


class PlanResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plan_id: str
    workflow_id: str
    turn_id: str
    parent_plan_id: str | None
    current_task_id: str | None
    status: str
    revision: int
    failure_code: str | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime


class TaskResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: str
    plan_id: str
    turn_id: str
    task_ref: str
    capability_code: str
    input_json: dict
    sequence: int
    status: str
    attempt_count: int
    max_attempts: int
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
    workflow_id: str | None = Field(default=None, min_length=1, max_length=100)
    parent_plan_id: str | None = Field(default=None, min_length=1, max_length=100)


class PlannerContextInput(_PlanningInput):
    """Planner 主输入；当前请求与历史读取集合严格分离。"""

    current_user_input: str = Field(min_length=1)
    context_chains: list[ContextChain] = Field(default_factory=list)


class RunPlanningResult(BaseModel):
    plan_id: str
    turn_id: str
    status: PlanStatus
    task_ids: list[str]
    failure_reason: str | None
    clarification_question: str | None = None
