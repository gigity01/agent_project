"""数据库工作单元抽象基类定义模块。

职责说明：
- 定义 `AbstractUnitOfWork` 抽象基类，规范 Unit of Work 模式的公共接口与上下文生命周期方法。
- 确立短数据库事务规范与约束：
  1. 必须由 Application Use Case 显式调用 `commit()`；
  2. 未调用 `commit()` 或抛出异常离开上下文时自动 `rollback()`；
  3. Repository 严禁自行管理事务。
"""

from abc import ABC, abstractmethod
from types import TracebackType


class AbstractUnitOfWork(ABC):
    """数据库事务工作单元抽象基类。

    一个 UnitOfWork 实例对应一个独立的短数据库事务。
    """

    @abstractmethod
    def __enter__(self) -> "AbstractUnitOfWork":
        """进入上下文，开启事务并返回当前工作单元实例。"""
        raise NotImplementedError

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        """退出上下文，执行异常回滚与连接释放。"""
        raise NotImplementedError

    @abstractmethod
    def flush(self) -> None:
        """刷新挂起的 SQL 变更到底层数据库连接（不提交事务）。"""
        raise NotImplementedError

    @abstractmethod
    def commit(self) -> None:
        """显式提交当前事务中的全部数据变更。"""
        raise NotImplementedError

    @abstractmethod
    def rollback(self) -> None:
        """回滚当前事务中的全部未提交数据变更。"""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """关闭当前会话并释放数据库连接。"""
        raise NotImplementedError
