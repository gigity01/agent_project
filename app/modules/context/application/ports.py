"""Context Application 层外部能力 Port。"""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import Any, AsyncContextManager, Protocol

from app.modules.context.application.dto import ContextAgentInput
from app.modules.context.domain.models import (
    ContextChain,
    ContextResourceQueue,
    ContextResourceRef,
    ContextSelectionDecision,
)


class ContextRouterPort(Protocol):
    async def route(
        self,
        agent_input: ContextAgentInput,
    ) -> ContextSelectionDecision:
        """返回 Planner 理解当前消息所需的历史读取集合。"""


class ConversationLockPort(Protocol):
    def hold(
        self,
        conversation_id: str,
    ) -> AsyncContextManager[None]:
        """获取 Conversation 级串行锁。"""


class ResourceQueuePort(Protocol):
    capacity: int

    async def get(
        self,
        *,
        conversation_id: str,
        chain_id: str,
        expected_version: int,
    ) -> ContextResourceQueue | None:
        """读取版本一致的资源热队列。"""

    async def replace(
        self,
        *,
        conversation_id: str,
        chain_id: str,
        resources: list[ContextResourceRef],
        database_version: int,
    ) -> None:
        """以数据库事实整体预热队列。"""

    async def refresh(
        self,
        *,
        conversation_id: str,
        chain_id: str,
        resources: list[ContextResourceRef],
        removed_resource_keys: list[str],
        expected_previous_version: int,
        database_version: int,
    ) -> bool:
        """按版本应用资源增量。"""

    async def invalidate(
        self,
        *,
        conversation_id: str,
        chain_id: str,
    ) -> None:
        """删除可丢弃的热队列缓存。"""


class ContextUnitOfWorkPort(Protocol):
    context: Any

    def __enter__(self) -> "ContextUnitOfWorkPort":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        ...

    def commit(self) -> None:
        ...


UnitOfWorkFactory = Callable[[], ContextUnitOfWorkPort]


class ContextChainMapperPort(Protocol):
    def __call__(
        self,
        chain: Any,
        *,
        resource_queue: ContextResourceQueue,
    ) -> ContextChain:
        """将持久化 Chain 完整映射为领域模型。"""


class ContextRecordFactoryPort(Protocol):
    def conversation_turn(self, **values: Any) -> Any:
        ...

    def context_selection_record(self, **values: Any) -> Any:
        ...

    def context_chain(self, **values: Any) -> Any:
        ...

    def context_chain_node(self, **values: Any) -> Any:
        ...

    def context_resource_event(self, **values: Any) -> Any:
        ...
