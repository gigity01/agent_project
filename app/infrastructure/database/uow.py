"""SQLAlchemy 事务工作单元实现（Unit of Work 模式）模块。

职责说明：
- 集中管理数据库 Session 的生命周期与跨模块 Repository 实例装配。
- 保证多仓储（Documents、Context、Plans、Tasks、Outbox 等）写操作在单一数据库短事务内原子提交或回滚。
- 强制遵循架构约束：Repository 严禁自行 commit/rollback，所有事务边界由 Use Case 显式通过 UoW 控制。
"""

from collections.abc import Callable
from types import TracebackType

from sqlalchemy.orm import Session

from app.infrastructure.database.session import session_local
from app.infrastructure.database.uow_base import AbstractUnitOfWork
from app.modules.context.infrastructure.persistence.repository import (
    ContextRepository,
)
from app.modules.context.infrastructure.persistence.conversation_turn_repository import (
    ConversationTurnRepository,
)
from app.modules.document.infrastructure.persistence.child_chunk_repository import (
    ChildChunkRepository,
)
from app.modules.document.infrastructure.persistence.document_artifact_repository import (
    DocumentArtifactRepository,
)
from app.modules.document.infrastructure.persistence.document_repository import (
    DocumentRepository,
)
from app.modules.document.infrastructure.persistence.parent_block_repository import (
    ParentBlockRepository,
)
from app.modules.document.infrastructure.persistence.knowledge_base_repository import (
    KnowledgeBaseRepository,
)
from app.modules.planning.infrastructure.persistence.plan_repository import (
    PlanRepository,
)
from app.modules.planning.infrastructure.persistence.task_repository import (
    TaskRepository,
)
from app.modules.planning.infrastructure.persistence.task_dependency_repository import (
    TaskDependencyRepository,
)
from app.modules.task_runtime.infrastructure.persistence.repository import (
    TaskExecutionRepository,
)
from app.modules.messaging.infrastructure.persistence.repository import (
    InboxRepository,
    OutboxRepository,
)
from app.modules.clarification.infrastructure.persistence.repository import (
    ClarificationRepository,
)

# 数据库会话工厂类型别名
SessionFactory = Callable[[], Session]


class SQLAlchemyUnitOfWork(AbstractUnitOfWork):
    """基于 SQLAlchemy Session 的具体工作单元实现。

    管理当前事务内的各领域仓储对象，提供上下文管理器协议以实现事务边界管理。
    """

    def __init__(self, session_factory: SessionFactory = session_local) -> None:
        """初始化工作单元。

        参数:
            session_factory: 数据库会话工厂可调用对象，默认使用全局 `session_local`。
        """
        self._session_factory = session_factory
        self._committed = False
        self._rolled_back = False
        self.session: Session | None = None

    def __enter__(self) -> "SQLAlchemyUnitOfWork":
        """进入上下文管理器：开启新 Session 并完成全部业务仓储对象的装配注入。

        返回:
            SQLAlchemyUnitOfWork: 已初始化活跃会话与仓储的工作单元实例。
        """
        self.session = self._session_factory()
        self._committed = False
        self._rolled_back = False

        # 装配各领域 Repository
        self.documents = DocumentRepository(self.session)
        self.knowledge_bases = KnowledgeBaseRepository(self.session)
        self.document_artifacts = DocumentArtifactRepository(self.session)
        self.parent_blocks = ParentBlockRepository(self.session)
        self.child_chunks = ChildChunkRepository(self.session)
        self.context = ContextRepository(self.session)
        self.plans = PlanRepository(self.session)
        self.tasks = TaskRepository(self.session)
        self.task_dependencies = TaskDependencyRepository(self.session)
        self.task_executions = TaskExecutionRepository(self.session)
        self.outbox = OutboxRepository(self.session)
        self.inbox = InboxRepository(self.session)
        self.clarifications = ClarificationRepository(self.session)
        self.conversation_turns = ConversationTurnRepository(self.session)

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        """退出上下文管理器：若发生未捕获异常或未显式 commit，自动执行 rollback 并安全关闭 Session。

        参数:
            exc_type: 异常类型。
            exc_value: 异常实例。
            traceback: 堆栈回溯对象。

        返回:
            bool: 始终返回 False，不吞没业务异常。
        """
        try:
            # 若抛出异常或尚未显式提交且未回滚，执行自动安全回滚
            if (exc_type is not None or not self._committed) and not self._rolled_back:
                self.rollback()
        finally:
            self.close()

        return False

    def flush(self) -> None:
        """将当前挂起的 ORM 变更刷新到底层数据库（生成自增 ID / 触发外键校验，但不提交事务）。"""
        self._get_session().flush()

    def commit(self) -> None:
        """显式提交当前数据库事务。若提交发生异常则自动回滚事务并向上抛出。

        异常:
            Exception: 底层数据库或 ORM 提交异常。
        """
        session = self._get_session()
        try:
            session.commit()
        except Exception:
            session.rollback()
            self._rolled_back = True
            raise
        self._committed = True

    def rollback(self) -> None:
        """回滚当前事务中的所有 SQL 变更并重置提交状态。"""
        self._get_session().rollback()
        self._committed = False
        self._rolled_back = True

    def close(self) -> None:
        """关闭当前会话并释放底层数据库连接回连接池。"""
        if self.session is not None:
            self.session.close()
            self.session = None

    def _get_session(self) -> Session:
        """获取当前活跃的 Session 实例。

        返回:
            Session: 数据库 Session 对象。

        异常:
            RuntimeError: 当在 `__enter__` 上下文之外调用时抛出。
        """
        if self.session is None:
            raise RuntimeError("Unit of Work 必须在 enter 上下文内使用")
        return self.session
