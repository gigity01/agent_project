"""Planner 可使用的 Planning Tool Catalog。

汇集供 Commit Agent 调用的所有 Planning 领域工具函数，
严格限制在 Plan 构建、校验发布与不支持标记等核心规划动作。
"""

from app.modules.planning.agent_tools.planning_tools import (
    create_build_chunks_task,
    create_index_vectors_task,
    create_process_document_task,
    finalize_plan,
    mark_plan_unsupported,
)


PLANNER_TOOLS = (
    create_process_document_task,
    create_build_chunks_task,
    create_index_vectors_task,
    finalize_plan,
    mark_plan_unsupported,
)
