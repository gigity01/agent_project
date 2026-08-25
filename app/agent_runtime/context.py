"""Agent Tool 的窄依赖调用上下文模块。

职责说明：
- 严格遵循最小权限与窄接口原则，定义各业务领域（Document、Context、Operations、Planning）暴露给 Agent Tool 的 Application Use Case 集合容器。
- 定义 `AgentToolContext` 数据类，贯穿单次 Agent Run 的调用生命周期，封装链路追踪标识（trace_id、agent_run_id 等）、授权范围、审计记录器及只读/写用例服务。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.agent_runtime.audit import AgentToolAuditLogger
from app.modules.context.application.query_service import ContextQueryService
from app.modules.context.application.use_cases import (
    GetContextChainUseCase,
    GetConversationTurnUseCase,
    ListContextChainNodesUseCase,
    ListContextChainResourcesUseCase,
    ListContextChainsUseCase,
    ListContextSelectionRecordsUseCase,
    ListConversationTurnsUseCase,
)
from app.modules.operations.application.query_service import OperationsQueryService
from app.modules.operations.application.use_cases import (
    GetDocumentOperationTimelineUseCase,
    GetDocumentWorkflowTimelineUseCase,
    QueryDocumentLogEventsUseCase,
)


if TYPE_CHECKING:
    from app.modules.planning.application.use_cases import (
        CreateBuildChunksTaskUseCase,
        CreateIndexVectorsTaskUseCase,
        CreateProcessDocumentTaskUseCase,
        FinalizePlanUseCase,
        MarkPlanUnsupportedUseCase,
        MarkPlanNeedsClarificationUseCase,
    )
from app.modules.document.application.use_cases.build_chunks import (
    BuildChunksUseCase,
)
from app.modules.document.application.use_cases.get_document import (
    GetDocumentUseCase,
)
from app.modules.document.application.use_cases.get_chunk_statistics import (
    GetDocumentChunkStatisticsUseCase,
)
from app.modules.document.application.use_cases.get_knowledge_base_statistics import (
    GetKnowledgeBaseStatisticsUseCase,
)
from app.modules.document.application.use_cases.get_pipeline_state import (
    GetDocumentPipelineStateUseCase,
)
from app.modules.document.application.use_cases.index_vectors import (
    IndexVectorsUseCase,
)
from app.modules.document.application.use_cases.list_artifacts import (
    ListDocumentArtifactsUseCase,
)
from app.modules.document.application.use_cases.list_child_chunks import (
    ListChildChunksUseCase,
)
from app.modules.document.application.use_cases.list_documents import (
    ListDocumentsUseCase,
)
from app.modules.document.application.use_cases.list_parent_blocks import (
    ListParentBlocksUseCase,
)
from app.modules.document.application.use_cases.process_document import (
    ProcessDocumentUseCase,
)
from app.modules.document.application.use_cases.search_artifacts import (
    SearchDocumentArtifactsUseCase,
)
from app.modules.document.application.use_cases.search_documents import (
    SearchDocumentsUseCase,
)


@dataclass(frozen=True)
class DocumentToolServices:
    """Document 模块暴露给 Tool 层的明确 Application Use Case 集合容器。

    包含文档查询、搜索、流水线状态、产物查询、切块分片与向量索引等用例。
    """

    get_document: GetDocumentUseCase
    list_documents: ListDocumentsUseCase
    search_documents: SearchDocumentsUseCase
    get_document_pipeline_state: GetDocumentPipelineStateUseCase
    list_document_artifacts: ListDocumentArtifactsUseCase
    search_document_artifacts: SearchDocumentArtifactsUseCase
    list_parent_blocks: ListParentBlocksUseCase
    list_child_chunks: ListChildChunksUseCase
    get_document_chunk_statistics: GetDocumentChunkStatisticsUseCase
    get_knowledge_base_statistics: GetKnowledgeBaseStatisticsUseCase
    process_document: ProcessDocumentUseCase
    build_chunks: BuildChunksUseCase
    index_vectors: IndexVectorsUseCase


@dataclass(frozen=True)
class ContextToolServices:
    """Context 模块暴露给 Tool 层的只读 Application Use Case 集合容器。

    包含上下文链、节点历史、关联资源与路由决策记录的只读查询能力。
    """

    query_service: ContextQueryService | None = None
    get_conversation_turn: GetConversationTurnUseCase | None = None
    list_conversation_turns: ListConversationTurnsUseCase | None = None
    get_context_chain: GetContextChainUseCase | None = None
    list_context_chains: ListContextChainsUseCase | None = None
    list_context_chain_nodes: ListContextChainNodesUseCase | None = None
    list_context_chain_resources: ListContextChainResourcesUseCase | None = None
    list_context_selection_records: (
        ListContextSelectionRecordsUseCase | None
    ) = None


@dataclass(frozen=True)
class OperationsToolServices:
    """Operations 模块暴露给 Tool 层的只读日志与时间线查询能力容器。"""

    query_service: OperationsQueryService | None = None
    query_document_log_events: QueryDocumentLogEventsUseCase | None = None
    get_document_operation_timeline: (
        GetDocumentOperationTimelineUseCase | None
    ) = None
    get_document_workflow_timeline: (
        GetDocumentWorkflowTimelineUseCase | None
    ) = None


@dataclass(frozen=True)
class PlanningToolServices:
    """Planning 模块暴露给 Planner Commit 阶段的明确 Task 创建与 Plan 终态提交用例容器。"""

    create_process_document_task: CreateProcessDocumentTaskUseCase
    create_build_chunks_task: CreateBuildChunksTaskUseCase
    create_index_vectors_task: CreateIndexVectorsTaskUseCase
    finalize_plan: FinalizePlanUseCase
    mark_plan_unsupported: MarkPlanUnsupportedUseCase
    mark_plan_needs_clarification: MarkPlanNeedsClarificationUseCase


@dataclass(frozen=True)
class AgentToolContext:
    """一次 Agent Run 中所有 Tool 共用的身份标识、权限集合与窄依赖上下文。

    字段说明：
    - trace_id: 全局分布式链路追踪唯一标识。
    - agent_run_id: 当前 Agent 运行轮次唯一标识。
    - agent_name: 当前执行 Agent 的角色名称。
    - conversation_id: 关联的会话 ID。
    - turn_id: 关联的对话轮次 ID。
    - task_id: 关联的 Task ID（执行器场景下非空）。
    - actor_code: 执行主体代码标识。
    - permissions: 当前授予的不可变权限集合。
    - document_services: Document 模块用例集合。
    - context_services: Context 模块用例集合。
    - planning_services: Planning 模块用例集合（仅 Planner 可用）。
    - plan_id: 关联的 Plan ID。
    - workflow_id: 关联的工作流 ID。
    - execution_id: TaskExecution 记录 ID。
    - operation_id: 当前操作锁与幂等令牌 ID。
    - task_document_id: Task 载荷中授权操作的目标文档 ID。
    - attempt: 当前任务或调用的重试尝试序号。
    - operations_services: Operations 模块日志查询服务集合。
    - allowed_context_chain_ids: 允许访问的 Context 链 ID 范围白名单。
    - allowed_context_turn_ids: 允许访问的 Context Turn ID 范围白名单。
    - audit_logger: 统一审计日志记录器。
    """

    trace_id: str
    agent_run_id: str
    agent_name: str
    conversation_id: str | None
    turn_id: str | None
    task_id: str | None
    actor_code: str
    permissions: frozenset[str]
    document_services: DocumentToolServices
    context_services: ContextToolServices
    planning_services: PlanningToolServices | None = None
    plan_id: str | None = None
    workflow_id: str | None = None
    execution_id: str | None = None
    operation_id: str | None = None
    task_document_id: int | None = None
    attempt: int = 1
    operations_services: OperationsToolServices = field(
        default_factory=OperationsToolServices
    )
    allowed_context_chain_ids: frozenset[str] = field(
        default_factory=frozenset
    )
    allowed_context_turn_ids: frozenset[str] = field(
        default_factory=frozenset
    )
    audit_logger: AgentToolAuditLogger = field(
        default_factory=AgentToolAuditLogger
    )
