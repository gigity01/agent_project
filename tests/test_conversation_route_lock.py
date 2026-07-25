"""Redis Conversation 路由锁的客户端所有权测试。"""

from __future__ import annotations

import unittest

from app.integrations.conversation_route_lock import (
    ConversationRouteLockManager,
    ConversationRouteLockUnavailable,
)


class _Lock:
    def __init__(self, *, acquired: bool = True) -> None:
        self.acquired = acquired
        self.acquire_count = 0
        self.release_count = 0

    async def acquire(self) -> bool:
        self.acquire_count += 1
        return self.acquired

    async def release(self) -> None:
        self.release_count += 1


class _RedisClient:
    def __init__(self, lock: _Lock) -> None:
        self.returned_lock = lock
        self.calls = []
        self.aclose_count = 0

    def lock(self, name: str, **kwargs):
        self.calls.append((name, kwargs))
        return self.returned_lock

    async def aclose(self) -> None:
        self.aclose_count += 1


class ConversationRouteLockManagerTest(
    unittest.IsolatedAsyncioTestCase
):
    async def test_uses_injected_client_without_owning_connection(self) -> None:
        lock = _Lock()
        client = _RedisClient(lock)
        manager = ConversationRouteLockManager(
            client,
            lock_timeout_seconds=30,
            blocking_timeout_seconds=2,
        )

        async with manager.hold("conversation-1"):
            self.assertEqual(lock.acquire_count, 1)

        self.assertEqual(lock.release_count, 1)
        self.assertEqual(client.aclose_count, 0)
        self.assertFalse(hasattr(manager, "aclose"))
        self.assertFalse(hasattr(manager, "from_url"))
        self.assertEqual(
            client.calls,
            [
                (
                    "context-route:conversation-1",
                    {
                        "timeout": 30,
                        "blocking_timeout": 2,
                        "thread_local": False,
                    },
                )
            ],
        )

    async def test_unavailable_lock_fails_without_entering_scope(self) -> None:
        client = _RedisClient(_Lock(acquired=False))
        manager = ConversationRouteLockManager(
            client,
            lock_timeout_seconds=30,
            blocking_timeout_seconds=2,
        )

        with self.assertRaisesRegex(
            ConversationRouteLockUnavailable,
            "conversation-1",
        ):
            async with manager.hold("conversation-1"):
                self.fail("锁获取失败时不应进入受保护作用域")


if __name__ == "__main__":
    unittest.main()
