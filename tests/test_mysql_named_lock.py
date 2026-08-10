"""MySQL named lock 外部副作用围栏测试。"""

from __future__ import annotations

import unittest

from app.infrastructure.database.named_lock import (
    ExternalEffectFenceError,
    MySQLNamedLockManager,
)


class _ScalarResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one(self):
        return self._value


class _Connection:
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
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    def connect(self) -> _Connection:
        return self.connection


class MySQLNamedLockManagerTest(unittest.TestCase):
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
