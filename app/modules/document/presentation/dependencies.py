"""文档 Presentation 层的 FastAPI 依赖。"""

from datetime import datetime
from typing import Literal

from fastapi import Depends, Form, Header, Response

from app.bootstrap.container import AppContainer
from app.bootstrap.dependencies import get_container
from app.modules.document.application.use_cases.build_chunks import (
    BuildChunksUseCase,
)
from app.modules.document.application.use_cases.get_chunk_statistics import (
    GetDocumentChunkStatisticsUseCase,
)
from app.modules.document.application.use_cases.get_document import (
    GetDocumentUseCase,
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
from app.modules.document.application.use_cases.upload_document import (
    UploadDocumentUseCase,
)
from app.modules.document.presentation.schemas import DocumentUploadFormData
from app.shared.observability.correlation import DocumentOperationContext


def get_document_operation_context(
    response: Response,
    workflow_id: str | None = Header(
        default=None,
        alias="X-Workflow-ID",
        min_length=1,
        max_length=200,
    ),
) -> DocumentOperationContext:
    """在管理 HTTP 边界创建上下文；重试次数与操作 ID 由后端持有。"""
    operation_context = DocumentOperationContext.create(workflow_id=workflow_id)
    response.headers["X-Workflow-ID"] = operation_context.workflow_id
    response.headers["X-Operation-ID"] = operation_context.operation_id
    response.headers["X-Operation-Attempt"] = str(operation_context.attempt)
    return operation_context


def document_upload_form(
    title: str = Form(...),
    kb_id: int = Form(...),
    domain_code: str = Form(...),
    business_scene: str | None = Form(None),
    risk_level: Literal["low", "medium", "high", "critical"] = Form("low"),
    effective_at: datetime | None = Form(None),
    expired_at: datetime | None = Form(None),
) -> DocumentUploadFormData:
    """将 multipart 表单字段组装为上传用例使用的元数据对象。"""
    return DocumentUploadFormData(
        title=title,
        kb_id=kb_id,
        domain_code=domain_code,
        business_scene=business_scene,
        risk_level=risk_level,
        effective_at=effective_at,
        expired_at=expired_at,
    )


def get_upload_document_use_case(
    container: AppContainer = Depends(get_container),
) -> UploadDocumentUseCase:
    return container.upload_document


def get_process_document_use_case(
    container: AppContainer = Depends(get_container),
) -> ProcessDocumentUseCase:
    return container.process_document


def get_build_chunks_use_case(
    container: AppContainer = Depends(get_container),
) -> BuildChunksUseCase:
    return container.build_chunks


def get_index_vectors_use_case(
    container: AppContainer = Depends(get_container),
) -> IndexVectorsUseCase:
    return container.index_vectors


def get_document_use_case(
    container: AppContainer = Depends(get_container),
) -> GetDocumentUseCase:
    return container.get_document


def get_search_documents_use_case(
    container: AppContainer = Depends(get_container),
) -> SearchDocumentsUseCase:
    return container.search_documents


def get_document_pipeline_state_use_case(
    container: AppContainer = Depends(get_container),
) -> GetDocumentPipelineStateUseCase:
    return container.get_document_pipeline_state


def get_list_document_artifacts_use_case(
    container: AppContainer = Depends(get_container),
) -> ListDocumentArtifactsUseCase:
    return container.list_document_artifacts


def get_search_document_artifacts_use_case(
    container: AppContainer = Depends(get_container),
) -> SearchDocumentArtifactsUseCase:
    return container.search_document_artifacts


def get_list_parent_blocks_use_case(
    container: AppContainer = Depends(get_container),
) -> ListParentBlocksUseCase:
    return container.list_parent_blocks


def get_list_child_chunks_use_case(
    container: AppContainer = Depends(get_container),
) -> ListChildChunksUseCase:
    return container.list_child_chunks


def get_document_chunk_statistics_use_case(
    container: AppContainer = Depends(get_container),
) -> GetDocumentChunkStatisticsUseCase:
    return container.get_document_chunk_statistics


def get_knowledge_base_statistics_use_case(
    container: AppContainer = Depends(get_container),
) -> GetKnowledgeBaseStatisticsUseCase:
    return container.get_knowledge_base_statistics
