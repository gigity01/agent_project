"""Task Runtime 端口与 Registry 定义。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from app.modules.task_runtime.application.dto import (
    TaskExecutorResult,
    TaskRuntimeContext,
)


class TaskExecutorPort(Protocol):
    async def execute(
        self,
        payload: BaseModel,
        context: TaskRuntimeContext,
    ) -> TaskExecutorResult:
        ...


class CapabilityDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    capability_code: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    executor_code: str
    max_attempts: int
    timeout_seconds: int
    side_effect: bool


class CapabilityRegistry:
    def __init__(self, definitions: list[CapabilityDefinition]) -> None:
        self._definitions = {
            definition.capability_code: definition
            for definition in definitions
        }
        if len(self._definitions) != len(definitions):
            raise ValueError("CapabilityDefinition capability_code 不得重复")

    def require(self, capability_code: str) -> CapabilityDefinition:
        try:
            return self._definitions[capability_code]
        except KeyError as exc:
            raise ValueError(f"未知 Capability: {capability_code}") from exc


class ExecutorRegistry:
    def __init__(self, executors: dict[str, TaskExecutorPort]) -> None:
        self._executors = dict(executors)

    def require(self, executor_code: str) -> TaskExecutorPort:
        try:
            return self._executors[executor_code]
        except KeyError as exc:
            raise ValueError(f"未知 Executor: {executor_code}") from exc


@dataclass(frozen=True)
class TaskRuntimePorts:
    uow_factory: Callable[[], Any]
    task_execution_factory: Callable[..., Any]
    outbox_event_factory: Callable[..., Any]
    inbox_event_factory: Callable[..., Any]
