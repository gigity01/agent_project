"""用于本地初始化 ORM 已注册表结构的辅助入口。"""

from app.infrastructure.database.session import Base, engine

from app.modules.document.infrastructure.persistence.models.document import Document
from app.modules.document.infrastructure.persistence.models.knowledge_base import (
    KnowledgeBase,
)


def init_db() -> None:
    """依据已导入的 ORM 模型创建缺失的数据表。"""
    Base.metadata.create_all(bind=engine)
