"""构建文档切块应用用例：以短事务编排领取、执行与结果登记。

流水线阶段 3：Build Chunks
负责从 cleaned 文本构建层次化父语义块（ParentBlock）与可向量化子块（ChildChunk）：
1. Claim 短事务：以行锁锁定 Document，复核状态必须为 processed（或满足无已有切块的 failed 状态重试条件），
   更新为 chunking 状态并写入当前 operation_id 作为 ownership token。
2. 事务外切块：
   - 依据 cleaned 文本格式分发至对应的 Chunker（TextChunker, MarkdownChunker, CsvChunker）
   - 构建父块（ParentBlockData）与子块（ChildChunkData），生成包含标题上下文的 embedding_text
   - 严密校验切块结果（父子块非空、序号连续唯一、无孤立引用、embedding_text 非空）
3. Finalize 短事务：再次锁定 Document 复核状态与 ownership，先批量删除旧 child chunks，
   再批量删除旧 parent blocks，批量持久化新父块与新子块（初始 vector_status='pending'），
   将 Document 推进为 chunked 并释放 ownership。

若失败，由 BuildChunksCompensator 校验 ownership 并将 Document 置为 failed。
"""

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


# 允许执行切块的业务生命周期状态集合
CHUNKABLE_LIFECYCLE_STATUSES = frozenset(
    {
        DocumentLifecycleStatus.ACTIVE.value,
        DocumentLifecycleStatus.SCHEDULED.value,
    }
)


class ChunkingAbortedError(RuntimeError):
    """表示切块执行或完成期间文档状态/ownership 发生非预期变化，切块结果不得登记。"""


@dataclass(frozen=True)
class ChunkingContext:
    """领取事务提交后传递给事务外切块计算阶段的不可变文档快照。

    Attributes:
        document_id: 文档自增 ID。
        doc_code: 文档业务编码。
        source_type: 原始文件类型。
        cleaned_path: 清洗后文本文件绝对路径。
        chunk_source_type: 清洗文本格式类型（如 'md', 'txt', 'csv'）。
        document_title: 文档标题（用于丰富 embedding_text 上下文）。
        kb_id: 所属知识库 ID。
        domain_code: 业务领域编码。
        business_scene: 业务场景标识。
        version: 文档版本号。
        process_metadata: 处理阶段附加元数据。
        status_before: 领取前状态。
        operation_id: 本次切块操作 ID。
    """

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
    """事务外生成、等待在完成短事务中持久化的父子切块数据集合。

    Attributes:
        context: 切块上下文。
        chunks: 切块器构建产出的父子块结果。
    """

    context: ChunkingContext
    chunks: ChunkBuildResult


def generate_parent_code(doc_code: str, block_index: int) -> str:
    """为文档内的父语义块生成唯一且包含顺序的业务编号。

    格式形如：PB_DOC_20260825_0001_ABC123

    Args:
        doc_code: 文档业务编码。
        block_index: 父块序号（0-based）。

    Returns:
        生成的父块业务编码。
    """
    return f"PB_{doc_code}_{block_index:04d}_{uuid4().hex[:6].upper()}"


def generate_chunk_code(
    doc_code: str,
    parent_index: int,
    chunk_index: int,
) -> str:
    """为父块内的子切块生成唯一且包含父子序号的业务编号。

    格式形如：CK_DOC_20260825_0001_0002_ABC123

    Args:
        doc_code: 文档业务编码。
        parent_index: 所属父块序号。
        chunk_index: 子块序号。

    Returns:
        生成的子块业务编码。
    """
    return (
        f"CK_{doc_code}_{parent_index:04d}_"
        f"{chunk_index:04d}_{uuid4().hex[:6].upper()}"
    )


class BuildChunksUseCase:
    """在短事务与事务外切块引擎之间编排父块与子块构建的用例入口。"""

    def __init__(self, *, ports: DocumentApplicationPorts) -> None:
        """初始化切块用例。

        Args:
            ports: 外部依赖端口容器。
        """
        self._ports = ports

    def execute(
        self,
        document_id: int,
        *,
        operation_context: DocumentOperationContext | None = None,
    ) -> BuildChunksResult:
        """同步执行文档切块流程（Claim -> Execute -> Finalize）。

        Args:
            document_id: 待切块的文档 ID。
            operation_context: 可选的操作上下文追踪信息。

        Returns:
            BuildChunksResult: 包含生成父子块数量的切块结果 DTO。

        Raises:
            DocumentApplicationError: 状态不合法（409）、未找到（404）或切块异常（400/500）。
        """
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
        # 阶段 1：短事务行锁领取切块权（校验三状态轴，更新为 chunking 与 operation_id）
        context = _claim_chunking(
            document_id,
            operation_id=operation_id,
            ports=ports,
        )
        chunk_logger.claimed(context)

        # 阶段 2：事务外读取 cleaned 文件，根据格式调度 Chunker 构建父子块
        phase = "execute"
        execution_result = _execute_chunking(
            context,
            ports=ports,
            chunk_logger=chunk_logger,
        )

        # 阶段 3：短事务完成登记（先删旧 child、再删旧 parent，批量落盘新块，推进为 chunked）
        phase = "finalize"
        response = _complete_chunking(execution_result, ports=ports)
        chunk_logger.completed(response)
        return response
    except ChunkingAbortedError as exc:
        chunk_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            state_updated=False,
            status_before=None,
            status_after=None,
        )
        raise DocumentApplicationError(
            status_code=409,
            detail=str(exc),
        ) from exc
    except DocumentApplicationError as exc:
        chunk_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            state_updated=False,
            status_before=None,
            status_after=None,
        )
        raise
    except Exception as exc:
        chunk_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            state_updated=False,
            status_before=None,
            status_after=None,
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
    """以行锁领取切块权，并立即提交 chunking 状态。

    业务规则：
    - 文档必须存在（404）
    - 无未释放的 active_operation_id（409）
    - 文档状态必须为 processed；若为 failed，必须满足无已有切块结果才允许从切块重试（已有切块必须走索引重试）
    - 业务生命周期必须有效（active / scheduled）
    - 存储状态必须为 active

    Args:
        document_id: 文档 ID。
        operation_id: 本次操作唯一 ID。
        ports: 端口容器。

    Returns:
        ChunkingContext: 领取成功后的不可变快照。
    """
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
        # failed 状态文档重试保护：若已有 ChildChunk 则不允许从切块重试，必须由索引阶段处理
        if (
            document.status == DocumentStatus.FAILED.value
            and uow.child_chunks.exists_by_doc_id(document.id)
        ):
            raise DocumentApplicationError(
                status_code=409,
                detail="文档已有切块结果，不能通过切块接口重试",
            )

        # 获取最新的 active cleaned 文本产物
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
            # 兼容历史数据直接读取 cleaned_uri 字段
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
    """在数据库事务外读取 cleaned 文件并调用 Chunker 生成父子块内存 DTO。

    Args:
        context: 切块上下文。
        ports: 端口容器。
        chunk_logger: 可选日志记录器。

    Returns:
        ChunkingExecutionResult: 切块执行结果。
    """
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
    # 严格校验切块产物完整性与索引唯一性
    _validate_chunk_build_result(chunks)
    result = ChunkingExecutionResult(context=context, chunks=chunks)
    if chunk_logger is not None:
        chunk_logger.build_completed(result, chunker=chunker_name)
    return result


def _validate_chunk_build_result(chunks: ChunkBuildResult) -> None:
    """严格校验切块结果的合法性，拒绝无法持久化或无法向量化的残缺结果。

    校验项：
    1. 必须生成至少一个父块与至少一个子块。
    2. 父块 block_index 必须全局唯一。
    3. 子块所属的父块索引必须全部存在于父块列表中。
    4. 各父块内部的子块 chunk_index 必须唯一。
    5. 所有子块的 embedding_text 必须为非空非空白字符串。

    Args:
        chunks: 待校验的切块结果。

    Raises:
        DocumentApplicationError: 校验不通过时抛出。
    """
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
    """在短事务中复核状态、删除旧块、持久化新父子块并推进状态到 chunked。

    Args:
        result: 切块执行结果。
        ports: 端口容器。

    Returns:
        BuildChunksResult: 完成结果 DTO。
    """
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

        # 在同一事务中先清旧 child chunks、再清旧 parent blocks，确保外键与数据一致性
        uow.child_chunks.delete_by_doc_id(document.id)
        uow.parent_blocks.delete_by_doc_id(document.id)

        # 批量持久化新父级语义块
        parent_blocks = [
            _build_parent_block(context, parent_data, ports=ports)
            for parent_data in result.chunks.parents
        ]
        saved_parents = uow.parent_blocks.create_many(parent_blocks)
        parents_by_block_index = {
            parent.block_index: parent for parent in saved_parents
        }

        # 批量持久化新可向量化子块（初始 vector_status 统一置为 'pending'）
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

        # 更新状态为 chunked，清空 active_operation_id 释放 ownership
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


def _fail_chunking(
    document_id: int,
    error: Exception,
    *,
    operation_id: str,
    ports: DocumentApplicationPorts,
) -> FailureStateResult:
    """仅在任务仍处于 chunking 且由指定 operation_id 持有时，标记为 failed 并释放 ownership。

    Args:
        document_id: 文档 ID。
        error: 错误对象。
        operation_id: 操作 ID。
        ports: 端口容器。

    Returns:
        FailureStateResult: 状态变更快照。
    """
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
    """回收指定切块 Operation 的 Document ownership 并标记失败的确定性补偿器。"""

    def __init__(self, *, ports: DocumentApplicationPorts) -> None:
        """初始化切块补偿器。

        Args:
            ports: 端口容器。
        """
        self._ports = ports

    def compensate(
        self,
        *,
        document_id: int,
        operation_id: str,
    ) -> FailureStateResult:
        """执行切块失败的补偿动作。

        Args:
            document_id: 文档 ID。
            operation_id: 需补偿的操作 ID。

        Returns:
            FailureStateResult: 状态变更快照。
        """
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
    """把事务外父块内存数据（ParentBlockData）转换为待持久化的 ORM 实体。

    Args:
        context: 切块上下文。
        parent_data: 内存父块数据。
        ports: 端口容器。

    Returns:
        持久化 ParentBlock 实体。
    """
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
    """把事务外子块内存数据（ChildChunkData）转换为待持久化的 ORM 实体。

    初始 vector_status 固定为 'pending'，等待向量索引阶段处理。

    Args:
        context: 切块上下文。
        parent_id: 所属父块持久化自增 ID。
        parent_index: 所属父块序号。
        child_data: 内存子块数据。
        ports: 端口容器。

    Returns:
        持久化 ChildChunk 实体。
    """
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
