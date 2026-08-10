"""构建文档切块应用用例：以短事务编排领取、执行与结果登记。"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.modules.document.application.dto import BuildChunksResult
from app.modules.document.application.errors import DocumentApplicationError
from app.modules.document.application.failure_state import (
    FailureStateResult,
    NO_FAILURE_STATE_CHANGE,
)
from app.modules.document.application.ports import DocumentApplicationPorts
from app.modules.document.domain.enums import (
    DocumentLifecycleStatus,
    DocumentStatus,
    DocumentStorageStatus,
)
from app.modules.document.domain.models import (
    ChildChunkData,
    ChunkBuildInput,
    ChunkBuildResult,
    ParentBlockData,
)
from app.modules.document.domain.policies import (
    get_expected_process_output_type,
    md5_text,
)
from app.shared.observability.document_chunk_logger import DocumentChunkLogger
from app.shared.observability.correlation import DocumentOperationContext


CHUNKABLE_LIFECYCLE_STATUSES = frozenset(
    {
        DocumentLifecycleStatus.ACTIVE.value,
        DocumentLifecycleStatus.SCHEDULED.value,
    }
)
logger = logging.getLogger(__name__)


class ChunkingAbortedError(RuntimeError):
    """表示切块执行期间文档状态变化，结果不得登记。"""


@dataclass(frozen=True)
class ChunkingContext:
    """领取事务提交后，事务外切块所需的不可变文档快照。"""

    document_id: int
    doc_code: str
    source_type: str
    cleaned_path: Path
    chunk_source_type: str
    document_title: str
    kb_id: int
    domain_code: str
    business_scene: str | None
    version: int
    process_metadata: dict[str, Any]
    status_before: str
    operation_id: str


@dataclass(frozen=True)
class ChunkingExecutionResult:
    """事务外生成、等待在完成事务中持久化的父子块数据。"""

    context: ChunkingContext
    chunks: ChunkBuildResult


def generate_parent_code(doc_code: str, block_index: int) -> str:
    """为文档内的父块生成可追踪的业务编号。"""
    return f"PB_{doc_code}_{block_index:04d}_{uuid4().hex[:6].upper()}"


def generate_chunk_code(
    doc_code: str,
    parent_index: int,
    chunk_index: int,
) -> str:
    """为父块内的子块生成可追踪的业务编号。"""
    return (
        f"CK_{doc_code}_{parent_index:04d}_"
        f"{chunk_index:04d}_{uuid4().hex[:6].upper()}"
    )


class BuildChunksUseCase:
    """在短事务之间编排父块与子块构建。"""

    def __init__(self, *, ports: DocumentApplicationPorts) -> None:
        self._ports = ports

    def execute(
        self,
        document_id: int,
        *,
        operation_context: DocumentOperationContext | None = None,
    ) -> BuildChunksResult:
        return _build_document_chunks(
            document_id,
            ports=self._ports,
            operation_context=operation_context,
        )


def _build_document_chunks(
    document_id: int,
    *,
    ports: DocumentApplicationPorts,
    operation_context: DocumentOperationContext | None = None,
) -> BuildChunksResult:
    """领取切块任务后在事务外计算，并以独立短事务登记结果。"""
    logger_kwargs = {"document_id": document_id}
    if operation_context is not None:
        logger_kwargs["operation_context"] = operation_context
    chunk_logger = DocumentChunkLogger(**logger_kwargs)
    operation_id = chunk_logger.operation_context.operation_id
    context: ChunkingContext | None = None
    phase = "claim"
    try:
        context = _claim_chunking(
            document_id,
            operation_id=operation_id,
            ports=ports,
        )
        chunk_logger.claimed(context)

        phase = "execute"
        execution_result = _execute_chunking(
            context,
            ports=ports,
            chunk_logger=chunk_logger,
        )

        phase = "finalize"
        response = _complete_chunking(execution_result, ports=ports)
        chunk_logger.completed(response)
        return response
    except ChunkingAbortedError as exc:
        failure_result = _register_chunking_failure(
            document_id=document_id,
            error=exc,
            claimed=context is not None,
            operation_id=operation_id,
            ports=ports,
        )
        chunk_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            state_updated=failure_result.state_updated,
            status_before=failure_result.status_before,
            status_after=failure_result.status_after,
        )
        raise DocumentApplicationError(
            status_code=409,
            detail=str(exc),
        ) from exc
    except DocumentApplicationError as exc:
        failure_result = _register_chunking_failure(
            document_id=document_id,
            error=exc,
            claimed=context is not None,
            operation_id=operation_id,
            ports=ports,
        )
        chunk_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            state_updated=failure_result.state_updated,
            status_before=failure_result.status_before,
            status_after=failure_result.status_after,
        )
        raise
    except Exception as exc:
        failure_result = _register_chunking_failure(
            document_id=document_id,
            error=exc,
            claimed=context is not None,
            operation_id=operation_id,
            ports=ports,
        )
        chunk_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            state_updated=failure_result.state_updated,
            status_before=failure_result.status_before,
            status_after=failure_result.status_after,
        )
        raise DocumentApplicationError(
            status_code=500,
            detail="构建 chunks 失败，请稍后重试或联系管理员",
        ) from exc


def _claim_chunking(
    document_id: int,
    *,
    operation_id: str,
    ports: DocumentApplicationPorts,
) -> ChunkingContext:
    """以行锁领取切块权，并立即提交 chunking 状态。"""
    with ports.uow_factory() as uow:
        document = uow.documents.get_by_id_for_update(document_id)

        if document is None:
            raise DocumentApplicationError(status_code=404, detail="文档不存在")
        if document.active_operation_id is not None:
            raise DocumentApplicationError(
                status_code=409,
                detail="文档已有未释放的切块 Operation",
            )
        if document.status not in {
            DocumentStatus.PROCESSED.value,
            DocumentStatus.FAILED.value,
        }:
            raise DocumentApplicationError(
                status_code=409,
                detail=f"当前文档状态不允许切块: {document.status}",
            )
        if document.lifecycle_status not in CHUNKABLE_LIFECYCLE_STATUSES:
            raise DocumentApplicationError(
                status_code=409,
                detail="失效文档不能切块",
            )
        if document.storage_status != DocumentStorageStatus.ACTIVE.value:
            raise DocumentApplicationError(
                status_code=409,
                detail="文档不在活跃存储区",
            )
        if (
            document.status == DocumentStatus.FAILED.value
            and uow.child_chunks.exists_by_doc_id(document.id)
        ):
            raise DocumentApplicationError(
                status_code=409,
                detail="文档已有切块结果，不能通过切块接口重试",
            )

        cleaned_artifact = uow.document_artifacts.get_latest_active(
            document_id=document.id,
            artifact_type="cleaned_text",
            artifact_role="process_output",
        )
        if cleaned_artifact is not None:
            cleaned_path = Path(cleaned_artifact.artifact_uri)
            chunk_source_type = cleaned_artifact.artifact_format
            process_metadata = dict(cleaned_artifact.metadata_json or {})
        else:
            # 兼容 Artifact 表接入前仅保留 cleaned_uri 的历史记录。
            if document.cleaned_uri is None:
                raise DocumentApplicationError(
                    status_code=400,
                    detail="文档尚未处理",
                )
            cleaned_path = Path(document.cleaned_uri)
            chunk_source_type = get_expected_process_output_type(
                document.source_type
            )
            process_metadata = {}

        status_before = document.status
        context = ChunkingContext(
            document_id=document.id,
            doc_code=document.doc_code,
            source_type=document.source_type,
            cleaned_path=cleaned_path,
            chunk_source_type=chunk_source_type,
            document_title=document.title,
            kb_id=document.kb_id,
            domain_code=document.domain_code,
            business_scene=document.business_scene,
            version=document.version,
            process_metadata=process_metadata,
            status_before=status_before,
            operation_id=operation_id,
        )
        document.status = DocumentStatus.CHUNKING.value
        document.active_operation_id = operation_id
        uow.flush()
        uow.commit()

    return context


def _execute_chunking(
    context: ChunkingContext,
    *,
    ports: DocumentApplicationPorts,
    chunk_logger: DocumentChunkLogger | None = None,
) -> ChunkingExecutionResult:
    """在数据库事务外读取 cleaned 文件并生成父子块 DTO。"""
    if not context.cleaned_path.exists():
        raise DocumentApplicationError(
            status_code=404,
            detail=f"cleaned 文件不存在: {context.cleaned_path}",
        )
    if not context.cleaned_path.is_file():
        raise DocumentApplicationError(
            status_code=400,
            detail=f"cleaned 路径不是有效文件: {context.cleaned_path}",
        )

    chunker = ports.chunker_factory(context.chunk_source_type)
    chunker_name = chunker.__class__.__name__
    if chunk_logger is not None:
        chunk_logger.build_started(context, chunker=chunker_name)
    chunks = chunker.build(
        ChunkBuildInput(
            cleaned_path=context.cleaned_path,
            document_title=context.document_title,
            business_scene=context.business_scene,
            process_metadata=context.process_metadata,
        )
    )
    _validate_chunk_build_result(chunks)
    result = ChunkingExecutionResult(context=context, chunks=chunks)
    if chunk_logger is not None:
        chunk_logger.build_completed(result, chunker=chunker_name)
    return result


def _validate_chunk_build_result(chunks: ChunkBuildResult) -> None:
    """拒绝无法安全持久化或无法进入向量索引阶段的切块结果。"""
    if not chunks.parents:
        raise DocumentApplicationError(
            status_code=400,
            detail="未生成任何 parent block",
        )

    parent_indices = [parent.block_index for parent in chunks.parents]
    parent_index_set = set(parent_indices)
    if len(parent_indices) != len(parent_index_set):
        raise DocumentApplicationError(
            status_code=500,
            detail="切块结果包含重复的 parent block_index",
        )

    child_count = sum(
        len(children)
        for children in chunks.children_by_parent_index.values()
    )
    if child_count == 0:
        raise DocumentApplicationError(
            status_code=400,
            detail="未生成任何 child chunk",
        )

    if set(chunks.children_by_parent_index) - parent_index_set:
        raise DocumentApplicationError(
            status_code=500,
            detail="切块结果引用了不存在的 parent block",
        )

    for children in chunks.children_by_parent_index.values():
        chunk_indices = [child.chunk_index for child in children]
        if len(chunk_indices) != len(set(chunk_indices)):
            raise DocumentApplicationError(
                status_code=500,
                detail="切块结果包含重复的 chunk_index",
            )
        if any(
            not child.embedding_text or not child.embedding_text.strip()
            for child in children
        ):
            raise DocumentApplicationError(
                status_code=500,
                detail="切块结果包含空的 embedding_text",
            )


def _complete_chunking(
    result: ChunkingExecutionResult,
    *,
    ports: DocumentApplicationPorts,
) -> BuildChunksResult:
    """在短事务中复核状态、替换父子块并推进到 chunked。"""
    context = result.context
    with ports.uow_factory() as uow:
        document = uow.documents.get_by_id_for_update(context.document_id)

        if document is None:
            raise DocumentApplicationError(status_code=404, detail="文档不存在")
        if document.status != DocumentStatus.CHUNKING.value:
            raise ChunkingAbortedError(
                f"文档切块状态已经变化: {document.status}"
            )
        if document.active_operation_id != context.operation_id:
            raise ChunkingAbortedError("当前切块 Operation 已被其他执行接管")
        if document.lifecycle_status not in CHUNKABLE_LIFECYCLE_STATUSES:
            raise ChunkingAbortedError("文档切块期间已经失效")
        if document.storage_status != DocumentStorageStatus.ACTIVE.value:
            raise ChunkingAbortedError("文档已进入归档流程")

        # 在同一事务中先清旧 child、再清旧 parent，随后批量写入新块。
        uow.child_chunks.delete_by_doc_id(document.id)
        uow.parent_blocks.delete_by_doc_id(document.id)

        parent_blocks = [
            _build_parent_block(context, parent_data, ports=ports)
            for parent_data in result.chunks.parents
        ]
        saved_parents = uow.parent_blocks.create_many(parent_blocks)
        parents_by_block_index = {
            parent.block_index: parent for parent in saved_parents
        }

        child_chunks: list[Any] = []
        for parent_data in result.chunks.parents:
            parent_block = parents_by_block_index[parent_data.block_index]
            for child_data in result.chunks.children_by_parent_index.get(
                parent_data.block_index,
                [],
            ):
                child_chunks.append(
                    _build_child_chunk(
                        context=context,
                        parent_id=parent_block.id,
                        parent_index=parent_data.block_index,
                        child_data=child_data,
                        ports=ports,
                    )
                )
        uow.child_chunks.create_many(child_chunks)

        document.status = DocumentStatus.CHUNKED.value
        document.active_operation_id = None
        uow.flush()
        response = BuildChunksResult(
            document_id=document.id,
            doc_code=document.doc_code,
            source_type=document.source_type,
            parent_count=len(parent_blocks),
            child_count=len(child_chunks),
            status="success",
        )
        uow.commit()

    return response


def _register_chunking_failure(
    *,
    document_id: int,
    error: Exception,
    claimed: bool,
    operation_id: str,
    ports: DocumentApplicationPorts,
) -> FailureStateResult:
    """尽力登记失败状态；登记异常时保留原始业务异常。"""
    if not claimed:
        return NO_FAILURE_STATE_CHANGE
    try:
        return BuildChunksCompensator(ports=ports).compensate(
            document_id=document_id,
            operation_id=operation_id,
        )
    except Exception:
        logger.exception(
            "文档切块失败状态登记失败",
            extra={"document_id": document_id},
        )
        return NO_FAILURE_STATE_CHANGE


def _fail_chunking(
    document_id: int,
    error: Exception,
    *,
    operation_id: str,
    ports: DocumentApplicationPorts,
) -> FailureStateResult:
    """仅在任务仍为 chunking 时，以独立短事务标记切块失败。"""
    del error
    with ports.uow_factory() as uow:
        document = uow.documents.get_by_id_for_update(document_id)
        if document is None:
            return NO_FAILURE_STATE_CHANGE
        status_before = document.status
        if (
            document.status == DocumentStatus.CHUNKING.value
            and document.active_operation_id == operation_id
        ):
            document.status = DocumentStatus.FAILED.value
            document.active_operation_id = None
            uow.flush()
            uow.commit()
            return FailureStateResult(
                state_updated=True,
                status_before=status_before,
                status_after=document.status,
            )
        return FailureStateResult(
            state_updated=False,
            status_before=status_before,
            status_after=document.status,
        )


class BuildChunksCompensator:
    """回收指定切块 Operation 的 Document ownership。"""

    def __init__(self, *, ports: DocumentApplicationPorts) -> None:
        self._ports = ports

    def compensate(
        self,
        *,
        document_id: int,
        operation_id: str,
    ) -> FailureStateResult:
        return _fail_chunking(
            document_id,
            RuntimeError("文档切块 Operation 需要补偿"),
            operation_id=operation_id,
            ports=self._ports,
        )


def _build_parent_block(
    context: ChunkingContext,
    parent_data: ParentBlockData,
    *,
    ports: DocumentApplicationPorts,
) -> Any:
    """把事务外父块 DTO 转换为待持久化 ORM 对象。"""
    return ports.parent_block_factory(
        parent_code=generate_parent_code(
            doc_code=context.doc_code,
            block_index=parent_data.block_index,
        ),
        kb_id=context.kb_id,
        doc_id=context.document_id,
        domain_code=context.domain_code,
        business_scene=context.business_scene,
        block_type=parent_data.block_type,
        title=parent_data.title,
        section_path=parent_data.section_path,
        content=parent_data.content,
        content_hash=md5_text(parent_data.content),
        block_index=parent_data.block_index,
        semantic_group_index=parent_data.semantic_group_index,
        segment_index=parent_data.segment_index,
        status="active",
        version=context.version,
    )


def _build_child_chunk(
    *,
    context: ChunkingContext,
    parent_id: int,
    parent_index: int,
    child_data: ChildChunkData,
    ports: DocumentApplicationPorts,
) -> Any:
    """把事务外子块 DTO 转换为待持久化 ORM 对象。"""
    return ports.child_chunk_factory(
        chunk_code=generate_chunk_code(
            doc_code=context.doc_code,
            parent_index=parent_index,
            chunk_index=child_data.chunk_index,
        ),
        parent_id=parent_id,
        doc_id=context.document_id,
        kb_id=context.kb_id,
        domain_code=context.domain_code,
        business_scene=context.business_scene,
        chunk_index=child_data.chunk_index,
        chunk_type=child_data.chunk_type,
        section_path=child_data.section_path,
        source_row_index=child_data.source_row_index,
        content=child_data.content,
        embedding_text=child_data.embedding_text,
        token_count=None,
        vector_status="pending",
        qdrant_point_id=None,
        status="active",
        version=context.version,
        indexed_at=None,
    )
