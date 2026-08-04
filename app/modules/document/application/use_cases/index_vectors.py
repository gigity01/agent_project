"""索引文档向量应用用例：以短事务编排领取、执行与结果登记。"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.modules.document.application.dto import IndexVectorsResult
from app.modules.document.application.errors import DocumentApplicationError
from app.modules.document.application.failure_state import (
    IndexFailureStateResult,
    NO_INDEX_FAILURE_STATE_CHANGE,
)
from app.modules.document.application.ports import DocumentApplicationPorts
from app.modules.document.application.settings import (
    DocumentIndexingSettings,
)
from app.modules.document.domain.enums import (
    DocumentLifecycleStatus,
    DocumentStatus,
    DocumentStorageStatus,
)
from app.shared.observability.document_index_logger import DocumentIndexLogger
from app.shared.observability.correlation import DocumentOperationContext
from app.shared.time import now_ms


logger = logging.getLogger(__name__)

INDEXABLE_LIFECYCLE_STATUSES = frozenset(
    {
        DocumentLifecycleStatus.ACTIVE.value,
        DocumentLifecycleStatus.SCHEDULED.value,
    }
)
INDEXABLE_VECTOR_STATUSES = frozenset({"pending", "failed"})


class EmbeddingClient(Protocol):
    """索引编排所需的最小 Embedding 客户端契约。"""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


class VectorStoreClient(Protocol):
    """索引编排所需的最小向量存储契约。"""

    def ensure_collection(self) -> None:
        ...

    def upsert_points(self, points: list[Any]) -> None:
        ...

    def delete_points(self, point_ids: list[int]) -> None:
        ...


class IndexingAbortedError(RuntimeError):
    """表示索引执行期间文档或子块状态变化，结果不得登记。"""


class IndexingExecutionError(RuntimeError):
    """携带失败操作位置和仅用于运行时补偿的 Point ID。"""

    def __init__(
        self,
        message: str,
        *,
        operation: str,
        batch_index: int | None,
        batch_size: int | None,
        confirmed_point_ids: tuple[int, ...],
        uncertain_point_ids: tuple[int, ...],
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.batch_index = batch_index
        self.batch_size = batch_size
        self.confirmed_point_ids = confirmed_point_ids
        self.uncertain_point_ids = uncertain_point_ids


@dataclass(frozen=True)
class IndexingChunkInput:
    """事务外生成向量所需的不可变子块快照。"""

    chunk_id: int
    chunk_code: str
    embedding_text: str
    parent_id: int
    doc_id: int
    kb_id: int
    domain_code: str
    business_scene: str | None
    chunk_index: int
    section_path: list[str] | None
    source_row_index: int | None


@dataclass(frozen=True)
class IndexingContext:
    """领取事务提交后，索引执行阶段使用的文档和子块快照。"""

    document_id: int
    source_type: str
    title: str
    original_filename: str | None
    chunks: tuple[IndexingChunkInput, ...]
    doc_code: str | None = None
    kb_id: int | None = None
    domain_code: str | None = None
    business_scene: str | None = None
    status_before: str | None = None
    pending_count: int = 0
    retry_count: int = 0


@dataclass(frozen=True)
class IndexingExecutionResult:
    """Qdrant upsert 完成、等待数据库登记的执行结果。"""

    context: IndexingContext
    point_ids: tuple[int, ...]


class IndexVectorsUseCase:
    """在短事务之间编排 Embedding 与 Qdrant 索引。"""

    def __init__(
        self,
        *,
        ports: DocumentApplicationPorts,
        settings: DocumentIndexingSettings,
    ) -> None:
        self._ports = ports
        self._settings = settings

    def execute(
        self,
        document_id: int,
        *,
        operation_context: DocumentOperationContext | None = None,
        embedding_client: EmbeddingClient | None = None,
        vector_store: VectorStoreClient | None = None,
    ) -> IndexVectorsResult:
        return _index_document_vectors(
            document_id,
            ports=self._ports,
            settings=self._settings,
            operation_context=operation_context,
            embedding_client=embedding_client,
            vector_store=vector_store,
        )


def _index_document_vectors(
    document_id: int,
    *,
    ports: DocumentApplicationPorts,
    settings: DocumentIndexingSettings,
    operation_context: DocumentOperationContext | None = None,
    embedding_client: EmbeddingClient | None = None,
    vector_store: VectorStoreClient | None = None,
) -> IndexVectorsResult:
    """领取索引任务，在事务外写 Qdrant，再以短事务登记结果。"""
    logger_kwargs = {"document_id": document_id}
    if operation_context is not None:
        logger_kwargs["operation_context"] = operation_context
    index_logger = DocumentIndexLogger(**logger_kwargs)
    context: IndexingContext | None = None
    resolved_vector_store = vector_store
    confirmed_point_ids: tuple[int, ...] = ()
    uncertain_point_ids: tuple[int, ...] = ()
    phase = "claim"

    try:
        context = _claim_indexing(document_id, ports=ports)
        index_logger.claimed(context)

        phase = "execute"
        resolved_embedding_client = (
            embedding_client or ports.embedding_factory()
        )
        resolved_vector_store = (
            resolved_vector_store or ports.vector_store_factory()
        )
        execution_result = _execute_indexing(
            context,
            embedding_client=resolved_embedding_client,
            vector_store=resolved_vector_store,
            index_logger=index_logger,
            ports=ports,
            settings=settings,
        )
        confirmed_point_ids = execution_result.point_ids

        phase = "finalize"
        response = _complete_indexing(execution_result, ports=ports)
        index_logger.completed(response)
        return response
    except IndexingExecutionError as exc:
        confirmed_point_ids = exc.confirmed_point_ids
        uncertain_point_ids = exc.uncertain_point_ids
        _handle_indexing_failure(
            document_id=document_id,
            context=context,
            phase=phase,
            confirmed_point_ids=confirmed_point_ids,
            uncertain_point_ids=uncertain_point_ids,
            vector_store=resolved_vector_store,
            error=exc,
            index_logger=index_logger,
            operation=exc.operation,
            batch_index=exc.batch_index,
            batch_size=exc.batch_size,
            ports=ports,
        )
        raise DocumentApplicationError(
            status_code=500,
            detail="向量索引失败，请稍后重试或联系管理员",
        ) from exc
    except IndexingAbortedError as exc:
        _handle_indexing_failure(
            document_id=document_id,
            context=context,
            phase=phase,
            confirmed_point_ids=confirmed_point_ids,
            uncertain_point_ids=uncertain_point_ids,
            vector_store=resolved_vector_store,
            error=exc,
            index_logger=index_logger,
            ports=ports,
        )
        raise DocumentApplicationError(
            status_code=409,
            detail=str(exc),
        ) from exc
    except DocumentApplicationError as exc:
        _handle_indexing_failure(
            document_id=document_id,
            context=context,
            phase=phase,
            confirmed_point_ids=confirmed_point_ids,
            uncertain_point_ids=uncertain_point_ids,
            vector_store=resolved_vector_store,
            error=exc,
            index_logger=index_logger,
            ports=ports,
        )
        raise
    except Exception as exc:
        _handle_indexing_failure(
            document_id=document_id,
            context=context,
            phase=phase,
            confirmed_point_ids=confirmed_point_ids,
            uncertain_point_ids=uncertain_point_ids,
            vector_store=resolved_vector_store,
            error=exc,
            index_logger=index_logger,
            ports=ports,
        )
        raise DocumentApplicationError(
            status_code=500,
            detail="向量索引失败，请稍后重试或联系管理员",
        ) from exc


def _claim_indexing(
    document_id: int,
    *,
    ports: DocumentApplicationPorts,
) -> IndexingContext:
    """以行锁领取索引权，并提交 Document/Chunk 的 indexing 状态。"""
    with ports.uow_factory() as uow:
        document = uow.documents.get_by_id_for_update(document_id)

        if document is None:
            raise DocumentApplicationError(status_code=404, detail="文档不存在")
        if document.status not in {
            DocumentStatus.CHUNKED.value,
            DocumentStatus.FAILED.value,
        }:
            raise DocumentApplicationError(
                status_code=409,
                detail=f"当前文档状态不允许索引: {document.status}",
            )
        if document.lifecycle_status not in INDEXABLE_LIFECYCLE_STATUSES:
            raise DocumentApplicationError(
                status_code=409,
                detail="失效文档不能索引",
            )
        if document.storage_status != DocumentStorageStatus.ACTIVE.value:
            raise DocumentApplicationError(
                status_code=409,
                detail="文档不在活跃存储区",
            )

        if uow.child_chunks.exists_by_doc_id_and_vector_status(
            document.id,
            "indexing",
        ):
            raise DocumentApplicationError(
                status_code=409,
                detail="文档存在未完成的索引任务，请先执行恢复操作",
            )

        chunks = uow.child_chunks.list_indexable_by_doc_id(
            document.id,
            set(INDEXABLE_VECTOR_STATUSES),
        )
        if not chunks:
            detail = (
                "文档没有可重试的向量块"
                if document.status == DocumentStatus.FAILED.value
                else "文档没有可索引的子块"
            )
            raise DocumentApplicationError(status_code=409, detail=detail)

        _validate_indexing_chunk_ownership(document, chunks)

        status_before = document.status
        pending_count = sum(
            chunk.vector_status == "pending" for chunk in chunks
        )
        retry_count = sum(
            chunk.vector_status == "failed" for chunk in chunks
        )
        context = IndexingContext(
            document_id=document.id,
            source_type=document.source_type,
            title=document.title,
            original_filename=document.original_filename,
            chunks=tuple(_to_chunk_input(chunk) for chunk in chunks),
            doc_code=document.doc_code,
            kb_id=document.kb_id,
            domain_code=document.domain_code,
            business_scene=document.business_scene,
            status_before=status_before,
            pending_count=pending_count,
            retry_count=retry_count,
        )
        uow.child_chunks.mark_indexing(chunks)
        document.status = DocumentStatus.INDEXING.value
        uow.flush()
        uow.commit()

    return context


def _execute_indexing(
    context: IndexingContext,
    *,
    embedding_client: EmbeddingClient,
    vector_store: VectorStoreClient,
    index_logger: DocumentIndexLogger | None = None,
    ports: DocumentApplicationPorts,
    settings: DocumentIndexingSettings,
) -> IndexingExecutionResult:
    """在数据库事务外分批生成向量并以稳定 ID upsert Qdrant。"""
    if settings.embedding_batch_size <= 0:
        raise IndexingExecutionError(
            "EMBEDDING_BATCH_SIZE 必须大于 0",
            operation="vector_validation",
            batch_index=None,
            batch_size=None,
            confirmed_point_ids=(),
            uncertain_point_ids=(),
        )

    confirmed_point_ids: list[int] = []
    try:
        vector_store.ensure_collection()
    except Exception as exc:
        raise IndexingExecutionError(
            "Qdrant Collection 检查失败",
            operation="collection_check",
            batch_index=None,
            batch_size=None,
            confirmed_point_ids=(),
            uncertain_point_ids=(),
        ) from exc

    if index_logger is not None:
        index_logger.collection_ready(
            collection_name=getattr(
                vector_store,
                "collection_name",
                None,
            ),
            vector_size=settings.embedding_vector_size,
        )

    for start in range(
        0,
        len(context.chunks),
        settings.embedding_batch_size,
    ):
        batch = context.chunks[
            start:start + settings.embedding_batch_size
        ]
        batch_index = start // settings.embedding_batch_size + 1
        batch_point_ids = [chunk.chunk_id for chunk in batch]
        embedding_started_at_ms = now_ms()
        if index_logger is not None:
            embedding_started_at_ms = index_logger.embedding_batch_started(
                batch_index=batch_index,
                batch_size=len(batch),
                embedding_model=settings.embedding_model_name,
            )
        try:
            vectors = embedding_client.embed_texts(
                [chunk.embedding_text for chunk in batch]
            )
        except Exception as exc:
            raise IndexingExecutionError(
                "Embedding 调用失败",
                operation="embedding",
                batch_index=batch_index,
                batch_size=len(batch),
                confirmed_point_ids=tuple(confirmed_point_ids),
                uncertain_point_ids=(),
            ) from exc

        try:
            _validate_vectors(batch, vectors, settings=settings)
            points = [
                _build_point(context, chunk, vector, ports=ports)
                for chunk, vector in zip(batch, vectors)
            ]
        except Exception as exc:
            raise IndexingExecutionError(
                "Embedding 结果校验失败",
                operation="vector_validation",
                batch_index=batch_index,
                batch_size=len(batch),
                confirmed_point_ids=tuple(confirmed_point_ids),
                uncertain_point_ids=(),
            ) from exc

        if index_logger is not None:
            index_logger.embedding_batch_completed(
                batch_index=batch_index,
                input_count=len(batch),
                vectors=vectors,
                started_at_ms=embedding_started_at_ms,
            )

        qdrant_started_at_ms = now_ms()
        try:
            vector_store.upsert_points(points)
        except Exception as exc:
            raise IndexingExecutionError(
                "Qdrant Upsert 失败",
                operation="qdrant_upsert",
                batch_index=batch_index,
                batch_size=len(batch),
                confirmed_point_ids=tuple(confirmed_point_ids),
                uncertain_point_ids=tuple(batch_point_ids),
            ) from exc

        confirmed_point_ids.extend(batch_point_ids)
        if index_logger is not None:
            index_logger.qdrant_batch_completed(
                batch_index=batch_index,
                point_count=len(batch_point_ids),
                started_at_ms=qdrant_started_at_ms,
            )

    return IndexingExecutionResult(
        context=context,
        point_ids=tuple(confirmed_point_ids),
    )


def _complete_indexing(
    result: IndexingExecutionResult,
    *,
    ports: DocumentApplicationPorts,
) -> IndexVectorsResult:
    """在短事务中复核文档和子块状态，并原子登记 indexed。"""
    context = result.context
    chunk_ids = _context_chunk_ids(context)
    with ports.uow_factory() as uow:
        document = uow.documents.get_by_id_for_update(context.document_id)

        if document is None:
            raise DocumentApplicationError(status_code=404, detail="文档不存在")
        if document.status != DocumentStatus.INDEXING.value:
            raise DocumentApplicationError(
                status_code=409,
                detail=f"文档索引状态已经变化: {document.status}",
            )
        if document.lifecycle_status not in INDEXABLE_LIFECYCLE_STATUSES:
            raise IndexingAbortedError("文档索引期间已经失效")
        if document.storage_status != DocumentStorageStatus.ACTIVE.value:
            raise IndexingAbortedError("文档已进入归档流程")

        chunks = uow.child_chunks.list_by_ids_for_update(
            document.id,
            chunk_ids,
        )
        if len(chunks) != len(chunk_ids) or any(
            chunk.vector_status != "indexing" for chunk in chunks
        ):
            raise IndexingAbortedError("索引子块状态已经变化")

        uow.child_chunks.mark_indexed_many(chunks)
        remaining_count = (
            uow.child_chunks.count_active_not_indexed_by_doc_id(document.id)
        )
        if remaining_count > 0:
            raise IndexingAbortedError("文档仍存在未完成索引的子块")

        document.status = DocumentStatus.INDEXED.value
        document.indexed_at = datetime.now()
        uow.flush()
        response = IndexVectorsResult(
            document_id=document.id,
            total_chunks=len(chunks),
            indexed_chunks=len(chunks),
            failed_chunks=0,
            status="success",
        )
        uow.commit()

    return response


def _fail_indexing(
    document_id: int,
    chunk_ids: tuple[int, ...],
    error: Exception,
    *,
    ports: DocumentApplicationPorts,
) -> IndexFailureStateResult:
    """以独立短事务把本次 indexing Document/Chunk 标记为 failed。"""
    del error
    with ports.uow_factory() as uow:
        document = uow.documents.get_by_id_for_update(document_id)
        if document is None:
            return NO_INDEX_FAILURE_STATE_CHANGE

        status_before = document.status
        chunks = uow.child_chunks.list_by_ids_for_update(
            document.id,
            chunk_ids,
        )
        chunk_statuses_before = [chunk.vector_status for chunk in chunks]
        uow.child_chunks.mark_failed(chunks)
        chunk_state_updated_count = sum(
            chunk_status_before != chunk.vector_status
            for chunk_status_before, chunk in zip(chunk_statuses_before, chunks)
        )
        if document.status == DocumentStatus.INDEXING.value:
            document.status = DocumentStatus.FAILED.value
        uow.flush()
        uow.commit()
        return IndexFailureStateResult(
            document_state_updated=status_before != document.status,
            chunk_state_updated_count=chunk_state_updated_count,
            status_before=status_before,
            status_after=document.status,
        )


def _handle_indexing_failure(
    *,
    document_id: int,
    context: IndexingContext | None,
    phase: str,
    confirmed_point_ids: tuple[int, ...],
    uncertain_point_ids: tuple[int, ...],
    vector_store: VectorStoreClient | None,
    error: Exception,
    index_logger: DocumentIndexLogger,
    operation: str | None = None,
    batch_index: int | None = None,
    batch_size: int | None = None,
    ports: DocumentApplicationPorts,
) -> IndexFailureStateResult:
    """不掩盖原异常地执行数据库失败登记和 Qdrant Point 补偿。"""
    failure_result = NO_INDEX_FAILURE_STATE_CHANGE
    if context is not None:
        try:
            failure_result = _fail_indexing(
                document_id,
                _context_chunk_ids(context),
                error,
                ports=ports,
            )
        except Exception:
            logger.exception(
                "向量索引失败状态登记失败",
                extra={"document_id": document_id},
            )

    index_logger.failed(
        error=error,
        phase=phase,
        context=context,
        document_state_updated=failure_result.document_state_updated,
        chunk_state_updated_count=failure_result.chunk_state_updated_count,
        status_before=failure_result.status_before,
        status_after=failure_result.status_after,
        operation=operation,
        batch_index=batch_index,
        batch_size=batch_size,
        confirmed_point_count=len(confirmed_point_ids),
        uncertain_point_count=len(uncertain_point_ids),
    )

    compensation_point_ids = tuple(
        dict.fromkeys(confirmed_point_ids + uncertain_point_ids)
    )
    if vector_store is None or not compensation_point_ids:
        return failure_result
    compensation_started_at_ms = now_ms()
    compensation_started_at_ms = index_logger.compensation_started(
        confirmed_point_count=len(confirmed_point_ids),
        uncertain_point_count=len(uncertain_point_ids),
    )
    try:
        vector_store.delete_points(list(compensation_point_ids))
        index_logger.compensation_completed(
            requested_point_count=len(compensation_point_ids),
            started_at_ms=compensation_started_at_ms,
        )
    except Exception as compensation_error:
        index_logger.compensation_failed(
            error=compensation_error,
            confirmed_point_count=len(confirmed_point_ids),
            uncertain_point_count=len(uncertain_point_ids),
            point_count=len(compensation_point_ids),
            started_at_ms=compensation_started_at_ms,
        )
        logger.exception(
            "Qdrant 索引补偿删除失败",
            extra={
                "document_id": document_id,
                "confirmed_point_count": len(confirmed_point_ids),
                "uncertain_point_count": len(uncertain_point_ids),
            },
        )
    return failure_result


def _validate_indexing_chunk_ownership(document, chunks) -> None:
    """确保待索引子块与 Document 的权威归属字段一致。"""
    if any(chunk.doc_id != document.id for chunk in chunks):
        raise RuntimeError("索引子块与文档关联不一致")
    if any(chunk.kb_id != document.kb_id for chunk in chunks):
        raise RuntimeError("索引子块与文档知识库不一致")
    if any(chunk.domain_code != document.domain_code for chunk in chunks):
        raise RuntimeError("索引子块与文档领域编码不一致")


def _to_chunk_input(chunk) -> IndexingChunkInput:
    """把 ORM 子块转换为事务外使用的不可变输入。"""
    return IndexingChunkInput(
        chunk_id=chunk.id,
        chunk_code=chunk.chunk_code,
        embedding_text=chunk.embedding_text,
        parent_id=chunk.parent_id,
        doc_id=chunk.doc_id,
        kb_id=chunk.kb_id,
        domain_code=chunk.domain_code,
        business_scene=chunk.business_scene,
        chunk_index=chunk.chunk_index,
        section_path=(
            list(chunk.section_path)
            if chunk.section_path is not None
            else None
        ),
        source_row_index=chunk.source_row_index,
    )


def _validate_vectors(
    chunks: tuple[IndexingChunkInput, ...],
    vectors: list[list[float]],
    *,
    settings: DocumentIndexingSettings,
) -> None:
    """校验一个批次的 Embedding 数量和维度。"""
    if len(vectors) != len(chunks):
        raise RuntimeError("Embedding 返回数量不一致")
    if any(
        len(vector) != settings.embedding_vector_size
        for vector in vectors
    ):
        raise RuntimeError("Embedding 维度不一致")


def _build_point(
    context: IndexingContext,
    chunk: IndexingChunkInput,
    vector: list[float],
    *,
    ports: DocumentApplicationPorts,
) -> Any:
    """使用 ChildChunk 主键构造可幂等 upsert 的 Qdrant Point。"""
    return ports.point_factory(
        id=chunk.chunk_id,
        vector=vector,
        payload={
            "document_id": chunk.doc_id,
            "kb_id": chunk.kb_id,
            "parent_block_id": chunk.parent_id,
            "child_chunk_id": chunk.chunk_id,
            "chunk_index": chunk.chunk_index,
            "chunk_code": chunk.chunk_code,
            "section_path": chunk.section_path,
            "source_row_index": chunk.source_row_index,
            "domain_code": chunk.domain_code,
            "business_scene": chunk.business_scene,
            "source_type": context.source_type,
            "title": context.title,
            "original_filename": context.original_filename,
        },
    )


def _context_chunk_ids(context: IndexingContext) -> tuple[int, ...]:
    return tuple(chunk.chunk_id for chunk in context.chunks)
