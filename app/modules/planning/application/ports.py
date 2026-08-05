"""Planning Application 使用的持久化 Port。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PlanningApplicationPorts:
    """由 Bootstrap 注入 Planning Use Case 的数据库能力。"""

    uow_factory: Callable[[], Any]
    plan_factory: Callable[..., Any]
    task_factory: Callable[..., Any]
