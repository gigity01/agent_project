from abc import ABC, abstractmethod
from types import TracebackType


class AbstractUnitOfWork(ABC):
    """
    一个 UnitOfWork 对应一个短数据库事务。

    约束：
    1. 必须显式调用 commit()。
    2. 未调用 commit()，离开上下文时自动 rollback。
    3. Repository 不允许自行 commit 或 rollback。
    """

    @abstractmethod
    def __enter__(self) -> "AbstractUnitOfWork":
        raise NotImplementedError

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        raise NotImplementedError

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
