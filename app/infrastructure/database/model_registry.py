"""全局 SQLAlchemy ORM 模型显式注册模块。

职责说明：
- 提供 `load_all_models()` 函数，显式导入系统各业务模块（Context、Document、Planning、Clarification、Messaging、Task Runtime）的全部持久化 ORM 模型。
- 确保在应用启动 (FastAPI / Worker) 或 Alembic 迁移执行时，所有表结构定义已完整注册至共享的 `Base.metadata`，避免外键关联或动态建表时由于未导入模型导致解析失败。
"""


def load_all_models() -> None:
    """显式导入系统所有领域的 ORM 模型模块，触发其元数据挂载至 Base.metadata。"""
    from app.modules.context.infrastructure.persistence import (
        models as context_models,
    )
    from app.modules.document.infrastructure.persistence.models import (
        child_chunk,
        document,
        document_artifact,
        knowledge_base,
        parent_block,
    )
    from app.modules.planning.infrastructure.persistence import (
        models as planning_models,
    )
    from app.modules.clarification.infrastructure.persistence import (
        models as clarification_models,
    )
    from app.modules.messaging.infrastructure.persistence import (
        models as messaging_models,
    )
    from app.modules.task_runtime.infrastructure.persistence import (
        models as task_runtime_models,
    )

    # 保留显式元组引用，防止 linter 警告未使用导入，并明确表达加载意图
    _ = (
        context_models,
        child_chunk,
        document,
        document_artifact,
        knowledge_base,
        parent_block,
        planning_models,
        clarification_models,
        messaging_models,
        task_runtime_models,
    )
