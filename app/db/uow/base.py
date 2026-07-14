# app/db/unit_of_work.py

from abc import ABC, abstractmethod
from collections.abc import Callable
from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session


SessionFactory = Callable[[], Session]


class AbstractUnitOfWork(ABC):
    """
    一个 UnitOfWork 对应一个短数据库事务。

    约束：
    1. 必须显式调用 commit()。
    2. 未调用 commit()，离开上下文时自动 rollback。
    3. Repository 不允许自行 commit 或 rollback。
    """

    @abstractmethod
    def __enter__(self) -> Self:
        raise NotImplementedError

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        try:
            # 无论是否发生异常，都回滚尚未提交的事务。
            # 已经 commit 的事务再次 rollback 不会撤销已提交内容。
            self.rollback()
        finally:
            self.close()

        # False 表示不吞掉异常。
        return False

    @abstractmethod
    def flush(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def commit(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError