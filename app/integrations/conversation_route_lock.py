"""基于 Redis 的 Conversation 级 Context 路由短锁。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis
from redis.exceptions import LockError

from app.modules.context.application.errors import (
    ConversationLockUnavailable,
)


ConversationRouteLockUnavailable = ConversationLockUnavailable


class ConversationRouteLockManager:
    """使用应用级共享 Redis 客户端串行化 Context 路由。"""

    def __init__(
        self,
        client: Redis,
        *,
        lock_timeout_seconds: int,
        blocking_timeout_seconds: int,
    ) -> None:
        if lock_timeout_seconds < 1:
            raise ValueError("Conversation route lock timeout must be positive")
        if blocking_timeout_seconds < 0:
            raise ValueError(
                "Conversation route blocking timeout cannot be negative"
            )
        self._client = client
        self._lock_timeout_seconds = lock_timeout_seconds
        self._blocking_timeout_seconds = blocking_timeout_seconds

    @asynccontextmanager
    async def hold(self, conversation_id: str) -> AsyncIterator[None]:
        lock = self._client.lock(
            f"ctx:{{{conversation_id}}}:route:lock",
            timeout=self._lock_timeout_seconds,
            blocking_timeout=self._blocking_timeout_seconds,
            thread_local=False,
        )
        acquired = await lock.acquire()
        if not acquired:
            raise ConversationRouteLockUnavailable(
                f"Conversation route lock unavailable: {conversation_id}"
            )

        try:
            yield
        finally:
            try:
                await lock.release()
            except LockError as exc:
                raise ConversationRouteLockUnavailable(
                    f"Conversation route lock expired: {conversation_id}"
                ) from exc
