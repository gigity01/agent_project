"""基于 Redis 的 Conversation 级 Context 路由短锁。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic_ns
from typing import Any

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
        event_logger: Any | None = None,
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
        self._event_logger = event_logger

    @asynccontextmanager
    async def hold(self, conversation_id: str) -> AsyncIterator[None]:
        wait_started_at = monotonic_ns()
        lock = self._client.lock(
            f"ctx:{{{conversation_id}}}:route:lock",
            timeout=self._lock_timeout_seconds,
            blocking_timeout=self._blocking_timeout_seconds,
            thread_local=False,
        )
        acquired = await lock.acquire()
        wait_duration_ms = self._elapsed_ms(wait_started_at)
        if not acquired:
            self._observe(
                "context_route_lock_unavailable",
                level="warning",
                conversation_id=conversation_id,
                context_route_lock_wait_duration=wait_duration_ms,
                context_route_lock_expired_count=0,
                duration_unit="milliseconds",
            )
            raise ConversationRouteLockUnavailable(
                f"Conversation route lock unavailable: {conversation_id}"
            )

        hold_started_at = monotonic_ns()
        self._observe(
            "context_route_lock_acquired",
            conversation_id=conversation_id,
            context_route_lock_wait_duration=wait_duration_ms,
            context_route_lock_expired_count=0,
            duration_unit="milliseconds",
        )
        try:
            yield
        finally:
            try:
                await lock.release()
            except LockError as exc:
                self._observe(
                    "context_route_lock_expired",
                    level="warning",
                    conversation_id=conversation_id,
                    context_route_lock_wait_duration=wait_duration_ms,
                    context_route_lock_hold_duration=self._elapsed_ms(
                        hold_started_at
                    ),
                    context_route_lock_expired_count=1,
                    duration_unit="milliseconds",
                )
                raise ConversationRouteLockUnavailable(
                    f"Conversation route lock expired: {conversation_id}"
                ) from exc
            self._observe(
                "context_route_lock_released",
                conversation_id=conversation_id,
                context_route_lock_wait_duration=wait_duration_ms,
                context_route_lock_hold_duration=self._elapsed_ms(
                    hold_started_at
                ),
                context_route_lock_expired_count=0,
                duration_unit="milliseconds",
            )

    @staticmethod
    def _elapsed_ms(started_at: int) -> float:
        return round((monotonic_ns() - started_at) / 1_000_000, 3)

    def _observe(self, event: str, **fields: Any) -> None:
        if self._event_logger is None:
            return
        try:
            self._event_logger.write(event, **fields)
        except Exception:
            # Observability is best-effort even when a custom logger is
            # injected. In particular, never strand an acquired Redis lock
            # because a metric sink failed before entering the protected
            # scope.
            return
