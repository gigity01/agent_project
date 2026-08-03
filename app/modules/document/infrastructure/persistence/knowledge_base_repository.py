"""知识库 ORM 模型的只读查询封装。"""

from sqlalchemy.orm import Session

from app.modules.document.infrastructure.persistence.models.knowledge_base import (
    KnowledgeBase,
)


class KnowledgeBaseRepository:
    """提供知识库查询入口，由应用层组合业务统计。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, kb_id: int) -> KnowledgeBase | None:
        return (
            self.db.query(KnowledgeBase)
            .filter(KnowledgeBase.id == kb_id)
            .first()
        )
