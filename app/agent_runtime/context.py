"""Agent Tool 的窄依赖调用上下文。"""

from dataclasses import dataclass, field

from app.agent_runtime.audit import AgentToolAuditLogger
from app.modules.document.application.use_cases.build_chunks import (
    BuildChunksUseCase,
)
from app.modules.document.application.use_cases.get_document import (
    GetDocumentUseCase,
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
from app.modules.document.application.use_cases.list_documents import (
    ListDocumentsUseCase,
)
from app.modules.document.application.use_cases.process_document import (
    ProcessDocumentUseCase,
)


@dataclass(frozen=True)
class DocumentToolServices:
    """Document Tool 可取得的明确 Application 能力集合。"""

    get_document: GetDocumentUseCase
    list_documents: ListDocumentsUseCase
    get_document_pipeline_state: GetDocumentPipelineStateUseCase
    list_document_artifacts: ListDocumentArtifactsUseCase
    process_document: ProcessDocumentUseCase
    build_chunks: BuildChunksUseCase
    index_vectors: IndexVectorsUseCase


@dataclass(frozen=True)
class ContextToolServices:
    """预留给后续 Context 只读 Tool 的窄服务集合。"""


@dataclass(frozen=True)
class AgentToolContext:
    """一次 Agent Run 中所有 Tool 共用的身份、权限与窄依赖。"""

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
    audit_logger: AgentToolAuditLogger = field(
        default_factory=AgentToolAuditLogger
    )
