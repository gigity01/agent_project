"""Agent Tool 的窄依赖调用上下文。"""

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
    ListContextRouteRecordsUseCase,
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
    """Document Tool 可取得的明确 Application 能力集合。"""

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
    """Context Tool 可取得的只读 Application 能力。"""

    query_service: ContextQueryService | None = None
    get_conversation_turn: GetConversationTurnUseCase | None = None
    list_conversation_turns: ListConversationTurnsUseCase | None = None
    get_context_chain: GetContextChainUseCase | None = None
    list_context_chains: ListContextChainsUseCase | None = None
    list_context_chain_nodes: ListContextChainNodesUseCase | None = None
    list_context_chain_resources: ListContextChainResourcesUseCase | None = None
    list_context_route_records: ListContextRouteRecordsUseCase | None = None


@dataclass(frozen=True)
class OperationsToolServices:
    """Operations Tool 可取得的只读日志查询能力。"""

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
    """Planner Tool 可调用的明确 Application 能力。"""

    create_process_document_task: CreateProcessDocumentTaskUseCase
    create_build_chunks_task: CreateBuildChunksTaskUseCase
    create_index_vectors_task: CreateIndexVectorsTaskUseCase
    finalize_plan: FinalizePlanUseCase
    mark_plan_unsupported: MarkPlanUnsupportedUseCase
    mark_plan_needs_clarification: MarkPlanNeedsClarificationUseCase


@dataclass(frozen=True)
class AgentToolContext:
    """一次 Agent Run 中所有 Tool 共用的身份、内部关联信息与窄依赖。"""

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
    attempt: int = 1
    operations_services: OperationsToolServices = field(
        default_factory=OperationsToolServices
    )
    audit_logger: AgentToolAuditLogger = field(
        default_factory=AgentToolAuditLogger
    )
