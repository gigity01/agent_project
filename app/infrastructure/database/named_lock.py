"""使用 MySQL connection-scoped named lock 实现跨进程副作用围栏。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.engine import Engine


class ExternalEffectFenceError(RuntimeError):
    """外部副作用围栏无法可靠获取或释放。"""


class MySQLNamedLockManager:
    """在同一数据库连接上获取并释放 MySQL named lock。"""

    def __init__(self, engine: Engine, *, timeout_seconds: int = 30) -> None:
        if timeout_seconds < 0:
            raise ValueError("named lock timeout_seconds 不能小于 0")
        self._engine = engine
        self._timeout_seconds = timeout_seconds

    @contextmanager
    def hold(self, resource_key: str) -> Iterator[None]:
        if not resource_key or len(resource_key) > 64:
            raise ValueError("MySQL named lock key 长度必须为 1 到 64")

        with self._engine.connect() as connection:
            acquired = connection.execute(
                text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
                {
                    "lock_name": resource_key,
                    "timeout_seconds": self._timeout_seconds,
                },
            ).scalar_one()
            if acquired != 1:
                raise ExternalEffectFenceError(
                    f"外部副作用围栏获取失败: {resource_key}"
                )

            try:
                yield
            finally:
                try:
                    released = connection.execute(
                        text("SELECT RELEASE_LOCK(:lock_name)"),
                        {"lock_name": resource_key},
                    ).scalar_one()
                except Exception as exc:
                    connection.invalidate()
                    raise ExternalEffectFenceError(
                        f"外部副作用围栏释放失败: {resource_key}"
                    ) from exc
                if released != 1:
                    connection.invalidate()
                    raise ExternalEffectFenceError(
                        f"外部副作用围栏释放失败: {resource_key}"
                    )
