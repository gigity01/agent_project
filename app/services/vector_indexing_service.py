"""以短事务编排文档向量索引的领取、执行与结果登记。"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fastapi import HTTPException
from qdrant_client.models import PointStruct

from app.app_config.settings import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MODEL_NAME,
    EMBEDDING_VECTOR_SIZE,
)
from app.constants.document_lifecycle_status import DocumentLifecycleStatus
from app.constants.document_status import DocumentStatus
from app.constants.document_storage_status import DocumentStorageStatus
from app.db.uow import SQLAlchemyUnitOfWork
from app.schemas.vector_indexing import VectorIndexingResponse
from app.services.embedding_service import EmbeddingService
from app.vectorstores.qdrant_store import QdrantVectorStore
from core.observability.document_index_logger import DocumentIndexLogger
from main_utils.times import now_ms


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

    def upsert_points(self, points: list[PointStruct]) -> None:
        ...

    def delete_points(self, point_ids: list[int]) -> None:
        ...


class IndexingAbortedError(RuntimeError):
    """表示索引执行期间文档或子块状态变化，结果不得登记。"""


class IndexingExecutionError(RuntimeError):
    """携带一次失败执行中已确认和结果不确定的 Qdrant Point ID。"""

    def __init__(
        self,
        message: str,
        *,
        confirmed_point_ids: tuple[int, ...],
        uncertain_point_ids: tuple[int, ...],
    ) -> None:
        super().__init__(message)
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


def index_document_vectors(
    document_id: int,
    *,
    embedding_client: EmbeddingClient | None = None,
    vector_store: VectorStoreClient | None = None,
) -> VectorIndexingResponse:
    """领取索引任务，在事务外写 Qdrant，再以短事务登记结果。"""
    index_logger = DocumentIndexLogger(document_id=document_id)
    context: IndexingContext | None = None
    resolved_vector_store = vector_store
    confirmed_point_ids: tuple[int, ...] = ()
    uncertain_point_ids: tuple[int, ...] = ()
    phase = "claim"

    try:
        context = _claim_indexing(document_id)
        index_logger.claimed(context)

        phase = "execute"
        resolved_embedding_client = embedding_client or EmbeddingService()
        resolved_vector_store = resolved_vector_store or QdrantVectorStore()
        execution_result = _execute_indexing(
            context,
            embedding_client=resolved_embedding_client,
            vector_store=resolved_vector_store,
            index_logger=index_logger,
        )
        confirmed_point_ids = execution_result.point_ids

        phase = "finalize"
        response = _complete_indexing(execution_result)
        index_logger.completed(response)
        return response
    except IndexingExecutionError as exc:
        confirmed_point_ids = exc.confirmed_point_ids
        uncertain_point_ids = exc.uncertain_point_ids
        index_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            confirmed_point_ids=confirmed_point_ids,
            uncertain_point_ids=uncertain_point_ids,
        )
        if context is not None:
            _handle_indexing_failure(
                document_id=document_id,
                chunk_ids=_context_chunk_ids(context),
                confirmed_point_ids=confirmed_point_ids,
                uncertain_point_ids=uncertain_point_ids,
                vector_store=resolved_vector_store,
                error=exc,
                index_logger=index_logger,
            )
        raise HTTPException(
            status_code=500,
            detail="向量索引失败，请稍后重试或联系管理员",
        ) from exc
    except IndexingAbortedError as exc:
        index_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            confirmed_point_ids=confirmed_point_ids,
            uncertain_point_ids=uncertain_point_ids,
        )
        if context is not None:
            _handle_indexing_failure(
                document_id=document_id,
                chunk_ids=_context_chunk_ids(context),
                confirmed_point_ids=confirmed_point_ids,
                uncertain_point_ids=uncertain_point_ids,
                vector_store=resolved_vector_store,
                error=exc,
                index_logger=index_logger,
            )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException as exc:
        index_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            confirmed_point_ids=confirmed_point_ids,
            uncertain_point_ids=uncertain_point_ids,
        )
        if context is not None:
            _handle_indexing_failure(
                document_id=document_id,
                chunk_ids=_context_chunk_ids(context),
                confirmed_point_ids=confirmed_point_ids,
                uncertain_point_ids=uncertain_point_ids,
                vector_store=resolved_vector_store,
                error=exc,
                index_logger=index_logger,
            )
        raise
    except Exception as exc:
        index_logger.failed(
            error=exc,
            phase=phase,
            context=context,
            confirmed_point_ids=confirmed_point_ids,
            uncertain_point_ids=uncertain_point_ids,
        )
        if context is not None:
            _handle_indexing_failure(
                document_id=document_id,
                chunk_ids=_context_chunk_ids(context),
                confirmed_point_ids=confirmed_point_ids,
                uncertain_point_ids=uncertain_point_ids,
                vector_store=resolved_vector_store,
                error=exc,
                index_logger=index_logger,
            )
        raise HTTPException(
            status_code=500,
            detail="向量索引失败，请稍后重试或联系管理员",
        ) from exc


def _claim_indexing(document_id: int) -> IndexingContext:
    """以行锁领取索引权，并提交 Document/Chunk 的 indexing 状态。"""
    with SQLAlchemyUnitOfWork() as uow:
        document = uow.documents.get_by_id_for_update(document_id)

        if document is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        if document.status not in {
            DocumentStatus.CHUNKED.value,
            DocumentStatus.FAILED.value,
        }:
            raise HTTPException(
                status_code=409,
                detail=f"当前文档状态不允许索引: {document.status}",
            )
        if document.lifecycle_status not in INDEXABLE_LIFECYCLE_STATUSES:
            raise HTTPException(status_code=409, detail="失效文档不能索引")
        if document.storage_status != DocumentStorageStatus.ACTIVE.value:
            raise HTTPException(status_code=409, detail="文档不在活跃存储区")

        if uow.child_chunks.exists_by_doc_id_and_vector_status(
            document.id,
            "indexing",
        ):
            raise HTTPException(
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
            raise HTTPException(status_code=409, detail=detail)

        status_before = document.status
        pending_count = sum(
            chunk.vector_status == "pending" for chunk in chunks
        )
        retry_count = sum(
            chunk.vector_status == "failed" for chunk in chunks
        )
        first_chunk = chunks[0]
        context = IndexingContext(
            document_id=document.id,
            source_type=document.source_type,
            title=document.title,
            original_filename=document.original_filename,
            chunks=tuple(_to_chunk_input(chunk) for chunk in chunks),
            doc_code=document.doc_code,
            kb_id=first_chunk.kb_id,
            domain_code=first_chunk.domain_code,
            business_scene=first_chunk.business_scene,
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
) -> IndexingExecutionResult:
    """在数据库事务外分批生成向量并以稳定 ID upsert Qdrant。"""
    if EMBEDDING_BATCH_SIZE <= 0:
        raise RuntimeError("EMBEDDING_BATCH_SIZE 必须大于 0")

    confirmed_point_ids: list[int] = []
    uncertain_point_ids: list[int] = []
    try:
        vector_store.ensure_collection()
        if index_logger is not None:
            index_logger.collection_ready(
                collection_name=getattr(
                    vector_store,
                    "collection_name",
                    None,
                ),
                vector_size=EMBEDDING_VECTOR_SIZE,
            )
        for start in range(0, len(context.chunks), EMBEDDING_BATCH_SIZE):
            batch = context.chunks[start:start + EMBEDDING_BATCH_SIZE]
            batch_index = start // EMBEDDING_BATCH_SIZE + 1
            batch_chunk_ids = [chunk.chunk_id for chunk in batch]
            embedding_started_at_ms = now_ms()
            if index_logger is not None:
                embedding_started_at_ms = index_logger.embedding_batch_started(
                    batch_index=batch_index,
                    chunk_ids=batch_chunk_ids,
                    embedding_model=EMBEDDING_MODEL_NAME,
                )
            vectors = embedding_client.embed_texts(
                [chunk.embedding_text for chunk in batch]
            )
            _validate_vectors(batch, vectors)
            if index_logger is not None:
                index_logger.embedding_batch_completed(
                    batch_index=batch_index,
                    input_count=len(batch),
                    vectors=vectors,
                    started_at_ms=embedding_started_at_ms,
                )

            points = [
                _build_point(context, chunk, vector)
                for chunk, vector in zip(batch, vectors)
            ]
            uncertain_point_ids = batch_chunk_ids
            qdrant_started_at_ms = now_ms()
            vector_store.upsert_points(points)
            confirmed_point_ids.extend(uncertain_point_ids)
            if index_logger is not None:
                index_logger.qdrant_batch_completed(
                    batch_index=batch_index,
                    point_ids=list(uncertain_point_ids),
                    started_at_ms=qdrant_started_at_ms,
                )
            uncertain_point_ids = []
    except Exception as exc:
        raise IndexingExecutionError(
            "事务外向量索引执行失败",
            confirmed_point_ids=tuple(confirmed_point_ids),
            uncertain_point_ids=tuple(uncertain_point_ids),
        ) from exc

    return IndexingExecutionResult(
        context=context,
        point_ids=tuple(confirmed_point_ids),
    )


def _complete_indexing(
    result: IndexingExecutionResult,
) -> VectorIndexingResponse:
    """在短事务中复核文档和子块状态，并原子登记 indexed。"""
    context = result.context
    chunk_ids = _context_chunk_ids(context)
    with SQLAlchemyUnitOfWork() as uow:
        document = uow.documents.get_by_id_for_update(context.document_id)

        if document is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        if document.status != DocumentStatus.INDEXING.value:
            raise HTTPException(
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
        response = VectorIndexingResponse(
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
) -> None:
    """以独立短事务把本次 indexing Document/Chunk 标记为 failed。"""
    del error
    with SQLAlchemyUnitOfWork() as uow:
        document = uow.documents.get_by_id_for_update(document_id)
        if document is None:
            return

        chunks = uow.child_chunks.list_by_ids_for_update(
            document.id,
            chunk_ids,
        )
        uow.child_chunks.mark_failed(chunks)
        if document.status == DocumentStatus.INDEXING.value:
            document.status = DocumentStatus.FAILED.value
        uow.flush()
        uow.commit()


def _handle_indexing_failure(
    *,
    document_id: int,
    chunk_ids: tuple[int, ...],
    confirmed_point_ids: tuple[int, ...],
    uncertain_point_ids: tuple[int, ...],
    vector_store: VectorStoreClient | None,
    error: Exception,
    index_logger: DocumentIndexLogger | None = None,
) -> None:
    """不掩盖原异常地执行数据库失败登记和 Qdrant Point 补偿。"""
    try:
        _fail_indexing(document_id, chunk_ids, error)
    except Exception:
        logger.exception(
            "向量索引失败状态登记失败",
            extra={"document_id": document_id},
        )

    compensation_point_ids = tuple(
        dict.fromkeys(confirmed_point_ids + uncertain_point_ids)
    )
    if vector_store is None or not compensation_point_ids:
        return
    compensation_started_at_ms = now_ms()
    if index_logger is not None:
        compensation_started_at_ms = index_logger.compensation_started(
            confirmed_point_ids=confirmed_point_ids,
            uncertain_point_ids=uncertain_point_ids,
        )
    try:
        vector_store.delete_points(list(compensation_point_ids))
        if index_logger is not None:
            index_logger.compensation_completed(
                confirmed_point_ids=confirmed_point_ids,
                uncertain_point_ids=uncertain_point_ids,
                started_at_ms=compensation_started_at_ms,
            )
    except Exception as compensation_error:
        if index_logger is not None:
            index_logger.compensation_failed(
                error=compensation_error,
                confirmed_point_ids=confirmed_point_ids,
                uncertain_point_ids=uncertain_point_ids,
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
) -> None:
    """校验一个批次的 Embedding 数量和维度。"""
    if len(vectors) != len(chunks):
        raise RuntimeError("Embedding 返回数量不一致")
    if any(len(vector) != EMBEDDING_VECTOR_SIZE for vector in vectors):
        raise RuntimeError("Embedding 维度不一致")


def _build_point(
    context: IndexingContext,
    chunk: IndexingChunkInput,
    vector: list[float],
) -> PointStruct:
    """使用 ChildChunk 主键构造可幂等 upsert 的 Qdrant Point。"""
    return PointStruct(
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
