"""用于本地初始化 ORM 已注册表结构的辅助入口。"""

from app.db.session import Base, engine

from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document


def init_db() -> None:
    """依据已导入的 ORM 模型创建缺失的数据表。"""
    Base.metadata.create_all(bind=engine)
