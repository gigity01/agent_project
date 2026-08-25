"""基于 MySQL connection-scoped 命名锁的外部副作用围栏实现模块。

职责说明：
- 利用 MySQL 的 `GET_LOCK(:lock_name, :timeout_seconds)` 和 `RELEASE_LOCK(:lock_name)` 函数，实现进程间排他命名锁（命名锁围栏）。
- 用于保护 Process 阶段文件目录提升/清理（`document:process:{document_id}`）与 Index 阶段 Qdrant 写入/删除（`document:index:{document_id}`），防止并发执行或故障恢复清理时发生副作用竞态。
- 采用独立数据库连接绑定锁生命周期，并在获取或释放异常时主动销毁连接 (`connection.invalidate()`)，防止锁残留。
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.engine import Engine


class ExternalEffectFenceError(RuntimeError):
    """外部副作用围栏无法可靠获取或释放时抛出的异常。"""


class MySQLNamedLockManager:
    """基于 MySQL 命名锁的分布式互斥围栏管理器。

    特点：
    - 命名锁与具体的 MySQL 连接会话绑定。
    - 超时未取得锁时抛出 `ExternalEffectFenceError`。
    - 释放锁失败时主动调用 `connection.invalidate()` 废弃底层连接，由 MySQL 服务端清理会话锁。
    """

    def __init__(self, engine: Engine, *, timeout_seconds: int = 30) -> None:
        """初始化命名锁管理器。

        参数:
            engine: SQLAlchemy Engine 引擎实例。
            timeout_seconds: 获取命名锁的最大阻塞超时时间（秒，默认 30 秒）。

        异常:
            ValueError: 当 timeout_seconds 小于 0 时抛出。
        """
        if timeout_seconds < 0:
            raise ValueError("named lock timeout_seconds 不能小于 0")
        self._engine = engine
        self._timeout_seconds = timeout_seconds

    @contextmanager
    def hold(self, resource_key: str) -> Iterator[None]:
        """上下文管理器：在专用连接上获取指定名称的 MySQL 命名锁，代码块退出时释放。

        参数:
            resource_key: 锁资源标识字符串（长度 1~64 字符，如 `document:process:101`）。

        异常:
            ValueError: 当 resource_key 长度不在 1~64 范围内时抛出。
            ExternalEffectFenceError: 当获取锁超时或释放锁失败时抛出。
        """
        if not resource_key or len(resource_key) > 64:
            raise ValueError("MySQL named lock key 长度必须为 1 到 64")

        with self._engine.connect() as connection:
            # 1. 尝试获取 MySQL 命名锁
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
                # 2. 释放 MySQL 命名锁
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
