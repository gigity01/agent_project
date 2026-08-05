"""Planner 可使用的 Planning Tool Catalog。"""

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
