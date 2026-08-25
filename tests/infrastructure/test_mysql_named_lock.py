"""基于 MySQL 命名锁（Named Lock）的外部副作用互斥围栏与连接失效测试。

核心业务不变量（遵循 AGENTS.md 规范）：
1. 命名锁语义（GET_LOCK / RELEASE_LOCK）：
   - 在同一个专用数据库连接上执行 `SELECT GET_LOCK(:lock_name, :timeout_seconds)` 获取围栏，并在退出上下文时执行 `SELECT RELEASE_LOCK(:lock_name)`。
   - 围栏用于保护跨存储副作用（如文件生成/提升 `document:process:{document_id}` 与 Qdrant 索引/删除 `document:index:{document_id}`）。
2. 异常与连接失效保护（Fail-closed & Invalidation）：
   - 超时未获取到锁时抛出 ExternalEffectFenceError 拒绝进入临界区。
   - 释放锁失败或报错时，主动调用 `connection.invalidate()` 使连接池丢弃该脏连接，防止未释放锁污染后续复用。
"""

from __future__ import annotations

import unittest

from app.infrastructure.database.named_lock import (
    ExternalEffectFenceError,
    MySQLNamedLockManager,
)


class _ScalarResult:
    """测试用 SQLAlchemy ScalarResult 替身。"""
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one(self):
        return self._value


class _Connection:
    """测试用数据库 Connection 替身，记录 SQL 执行历史并在异常时标记 invalidated。"""
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = []
        self.invalidated = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        return False

    def execute(self, statement, parameters):
        self.calls.append((str(statement), parameters))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return _ScalarResult(result)

    def invalidate(self) -> None:
        self.invalidated = True


class _Engine:
    """测试用 SQLAlchemy Engine 替身。"""
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def connect(self) -> _Connection:
        return self.connection


class MySQLNamedLockManagerTest(unittest.TestCase):
    """验证 MySQLNamedLockManager 的同连接获取/释放、超时拦截与连接失效。"""
    def test_holds_and_releases_lock_on_same_connection(self) -> None:
        connection = _Connection([1, 1])
        manager = MySQLNamedLockManager(_Engine(connection), timeout_seconds=7)

        with manager.hold("document:index:1"):
            pass

        self.assertIn("GET_LOCK", connection.calls[0][0])
        self.assertEqual(
            connection.calls[0][1],
            {"lock_name": "document:index:1", "timeout_seconds": 7},
        )
        self.assertIn("RELEASE_LOCK", connection.calls[1][0])
        self.assertFalse(connection.invalidated)

    def test_acquire_timeout_fails_closed(self) -> None:
        connection = _Connection([0])
        manager = MySQLNamedLockManager(_Engine(connection))

        with self.assertRaisesRegex(
            ExternalEffectFenceError,
            "围栏获取失败",
        ):
            with manager.hold("document:index:1"):
                self.fail("未获取围栏时不应进入临界区")

        self.assertEqual(len(connection.calls), 1)

    def test_release_failure_invalidates_connection(self) -> None:
        connection = _Connection([1, 0])
        manager = MySQLNamedLockManager(_Engine(connection))

        with self.assertRaisesRegex(
            ExternalEffectFenceError,
            "围栏释放失败",
        ):
            with manager.hold("document:index:1"):
                pass

        self.assertTrue(connection.invalidated)


if __name__ == "__main__":
    unittest.main()
