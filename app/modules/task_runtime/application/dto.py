"""Task Runtime 命令、快照与执行结果。"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ClaimNextTaskInput(BaseModel):
    plan_id: str = Field(min_length=1, max_length=100)


class TaskSnapshot(BaseModel):
    task_id: str
    plan_id: str
    workflow_id: str
    capability_code: str
    input_json: dict[str, Any]
    sequence: int
    attempt: int
    max_attempts: int
    execution_id: str
    operation_id: str
    executor_code: str


class ClaimNextTaskResult(BaseModel):
    outcome: Literal["claimed", "already_running", "no_task", "terminal"]
    task: TaskSnapshot | None = None


class TaskRuntimeContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    workflow_id: str
    plan_id: str
    task_id: str
    execution_id: str
    operation_id: str
    attempt: int


class TaskExecutorResult(BaseModel):
    output_json: dict[str, Any]
    resource_refs: list[str] = Field(default_factory=list)


class ExecutePlanResult(BaseModel):
    plan_id: str
    outcome: Literal[
        "task_succeeded",
        "retry_scheduled",
        "replan_requested",
        "already_running",
        "no_task",
        "terminal",
    ]
    task_id: str | None = None
    execution_id: str | None = None
