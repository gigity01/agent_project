from collections.abc import Callable
from types import TracebackType

from sqlalchemy.orm import Session

from app.infrastructure.database.session import session_local
from app.infrastructure.database.uow_base import AbstractUnitOfWork
from app.modules.context.infrastructure.persistence.repository import (
    ContextRepository,
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


SessionFactory = Callable[[], Session]


class SQLAlchemyUnitOfWork(AbstractUnitOfWork):
    """基于 SQLAlchemy Session 的工作单元。"""

    def __init__(self, session_factory: SessionFactory = session_local) -> None:
        self._session_factory = session_factory
        self._committed = False
        self._rolled_back = False
        self.session: Session | None = None

    def __enter__(self) -> "SQLAlchemyUnitOfWork":
        self.session = self._session_factory()
        self._committed = False
        self._rolled_back = False

        self.documents = DocumentRepository(self.session)
        self.document_artifacts = DocumentArtifactRepository(self.session)
        self.parent_blocks = ParentBlockRepository(self.session)
        self.child_chunks = ChildChunkRepository(self.session)
        self.context = ContextRepository(self.session)

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        try:
            if (exc_type is not None or not self._committed) and not self._rolled_back:
                self.rollback()
        finally:
            self.close()

        return False

    def flush(self) -> None:
        self._get_session().flush()

    def commit(self) -> None:
        session = self._get_session()
        try:
            session.commit()
        except Exception:
            session.rollback()
            self._rolled_back = True
            raise
        self._committed = True

    def rollback(self) -> None:
        self._get_session().rollback()
        self._committed = False
        self._rolled_back = True

    def close(self) -> None:
        if self.session is not None:
            self.session.close()
            self.session = None

    def _get_session(self) -> Session:
        if self.session is None:
            raise RuntimeError("Unit of Work must be entered before use")
        return self.session
