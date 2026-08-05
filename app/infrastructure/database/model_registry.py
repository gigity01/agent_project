"""集中注册应用所有 SQLAlchemy ORM 模型。"""


def load_all_models() -> None:
    """导入全部模型模块，确保其表已加入共享 Base.metadata。"""
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

    # 保留显式引用，使本函数的目的对静态检查器同样清晰。
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
