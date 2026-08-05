"""Planning Application 使用的持久化 Port。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class PlannerRunnerPort(Protocol):
    async def run(self, *, user_input: str, context: Any) -> Any:
        """运行 Planner；最终业务结果由 Application 重新读取数据库。"""


@dataclass(frozen=True)
class PlanningApplicationPorts:
    """由 Bootstrap 注入 Planning Use Case 的数据库能力。"""

    uow_factory: Callable[[], Any]
    plan_factory: Callable[..., Any]
    task_factory: Callable[..., Any]
    task_dependency_factory: Callable[..., Any]
    outbox_event_factory: Callable[..., Any]
    inbox_event_factory: Callable[..., Any]
    clarification_request_factory: Callable[..., Any]
    integrity_error_type: type[BaseException]

    def is_integrity_error(self, exc: BaseException) -> bool:
        return isinstance(exc, self.integrity_error_type)
