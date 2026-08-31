"""本地/测试环境数据库表结构初始化辅助脚本模块。

职责说明：
- 提供 `init_db()` 函数，直接调用 `Base.metadata.create_all(bind=engine)` 创建所有已注册的数据库表。
- 仅用于本地快速开发或离线测试，生产环境结构变更必须严格通过 Alembic 迁移脚本执行。
"""

from app.infrastructure.database.session import Base, engine

from app.modules.document.infrastructure.persistence.models.document import Document
from app.modules.document.infrastructure.persistence.models.knowledge_base import (
    KnowledgeBase,
)


def init_db() -> None:
    """根据当前已导入的 ORM 模型元数据，在绑定的数据库中同步创建所有缺失的数据表。"""
    Base.metadata.create_all(bind=engine)
