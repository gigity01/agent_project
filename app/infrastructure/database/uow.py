"""SQLAlchemy 事务工作单元实现（Unit of Work 模式）。

集中管理数据库 Session 的生命周期与跨模块 Repository 实例，
保证多仓储写操作在单一数据库事务内原子提交或回滚。
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


SessionFactory = Callable[[], Session]


class SQLAlchemyUnitOfWork(AbstractUnitOfWork):
    """基于 SQLAlchemy Session 的工作单元实现。"""

    def __init__(self, session_factory: SessionFactory = session_local) -> None:
        """初始化工作单元。

        Args:
            session_factory: 数据库会话工厂，默认绑定 session_local。
        """
        self._session_factory = session_factory
        self._committed = False
        self._rolled_back = False
        self.session: Session | None = None

    def __enter__(self) -> "SQLAlchemyUnitOfWork":
        """进入上下文管理器，创建新 Session 并装配各领域 Repository。"""
        self.session = self._session_factory()
        self._committed = False
        self._rolled_back = False

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
        """退出上下文，若发生异常或未显式 commit 则自动回滚并关闭 Session。"""
        try:
            if (exc_type is not None or not self._committed) and not self._rolled_back:
                self.rollback()
        finally:
            self.close()

        return False

    def flush(self) -> None:
        """将当前挂起的 SQL 变更刷新到底层数据库连接（不提交事务）。"""
        self._get_session().flush()

    def commit(self) -> None:
        """提交当前事务。若提交失败则自动回滚并抛出异常。"""
        session = self._get_session()
        try:
            session.commit()
        except Exception:
            session.rollback()
            self._rolled_back = True
            raise
        self._committed = True

    def rollback(self) -> None:
        """回滚当前事务中的所有变更。"""
        self._get_session().rollback()
        self._committed = False
        self._rolled_back = True

    def close(self) -> None:
        """关闭底层 Session 并释放连接。"""
        if self.session is not None:
            self.session.close()
            self.session = None

    def _get_session(self) -> Session:
        """获取当前活跃的 Session，若未进入上下文则报错。"""
        if self.session is None:
            raise RuntimeError("Unit of Work 必须在 enter 上下文内使用")
        return self.session
