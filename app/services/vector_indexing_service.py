"""以短事务编排文档向量索引的领取、执行与结果登记。"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from fastapi import HTTPException
from qdrant_client.models import PointStruct

from app.app_config.settings import (
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_VECTOR_SIZE,
)
from app.constants.document_lifecycle_status import DocumentLifecycleStatus
from app.constants.document_status import DocumentStatus
from app.constants.document_storage_status import DocumentStorageStatus
from app.db.uow import SQLAlchemyUnitOfWork
from app.schemas.vector_indexing import VectorIndexingResponse
from app.services.embedding_service import EmbeddingService
from app.vectorstores.qdrant_store import QdrantVectorStore


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

    def upsert_points(self, points: list[PointStruct]) -> None:
        ...

    def delete_points(self, point_ids: list[int]) -> None:
        ...


class IndexingAbortedError(RuntimeError):
    """表示索引执行期间文档或子块状态变化，结果不得登记。"""


class IndexingExecutionError(RuntimeError):
    """携带一次失败执行中可能已经写入 Qdrant 的 Point ID。"""

    def __init__(self, message: str, point_ids: tuple[int, ...]) -> None:
        super().__init__(message)
        self.point_ids = point_ids


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
    context = _claim_indexing(document_id)
    resolved_vector_store = vector_store
    point_ids: tuple[int, ...] = ()

    try:
        resolved_embedding_client = embedding_client or EmbeddingService()
        resolved_vector_store = resolved_vector_store or QdrantVectorStore()
        execution_result = _execute_indexing(
            context,
            embedding_client=resolved_embedding_client,
            vector_store=resolved_vector_store,
        )
        point_ids = execution_result.point_ids
        return _complete_indexing(execution_result)
    except IndexingExecutionError as exc:
        point_ids = exc.point_ids
        _handle_indexing_failure(
            document_id=document_id,
            chunk_ids=_context_chunk_ids(context),
            point_ids=point_ids,
            vector_store=resolved_vector_store,
            error=exc,
        )
        raise HTTPException(
            status_code=500,
            detail="向量索引失败，请稍后重试或联系管理员",
        ) from exc
    except IndexingAbortedError as exc:
        _handle_indexing_failure(
            document_id=document_id,
            chunk_ids=_context_chunk_ids(context),
            point_ids=point_ids,
            vector_store=resolved_vector_store,
            error=exc,
        )
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException as exc:
        _handle_indexing_failure(
            document_id=document_id,
            chunk_ids=_context_chunk_ids(context),
            point_ids=point_ids,
            vector_store=resolved_vector_store,
            error=exc,
        )
        raise
    except Exception as exc:
        _handle_indexing_failure(
            document_id=document_id,
            chunk_ids=_context_chunk_ids(context),
            point_ids=point_ids,
            vector_store=resolved_vector_store,
            error=exc,
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

        context = IndexingContext(
            document_id=document.id,
            source_type=document.source_type,
            title=document.title,
            original_filename=document.original_filename,
            chunks=tuple(_to_chunk_input(chunk) for chunk in chunks),
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
) -> IndexingExecutionResult:
    """在数据库事务外分批生成向量并以稳定 ID upsert Qdrant。"""
    if EMBEDDING_BATCH_SIZE <= 0:
        raise RuntimeError("EMBEDDING_BATCH_SIZE 必须大于 0")

    attempted_point_ids: list[int] = []
    try:
        for start in range(0, len(context.chunks), EMBEDDING_BATCH_SIZE):
            batch = context.chunks[start:start + EMBEDDING_BATCH_SIZE]
            vectors = embedding_client.embed_texts(
                [chunk.embedding_text for chunk in batch]
            )
            _validate_vectors(batch, vectors)

            points = [
                _build_point(context, chunk, vector)
                for chunk, vector in zip(batch, vectors)
            ]
            batch_point_ids = [chunk.chunk_id for chunk in batch]
            attempted_point_ids.extend(batch_point_ids)
            vector_store.upsert_points(points)
    except Exception as exc:
        raise IndexingExecutionError(
            "事务外向量索引执行失败",
            tuple(attempted_point_ids),
        ) from exc

    return IndexingExecutionResult(
        context=context,
        point_ids=tuple(attempted_point_ids),
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
    point_ids: tuple[int, ...],
    vector_store: VectorStoreClient | None,
    error: Exception,
) -> None:
    """不掩盖原异常地执行数据库失败登记和 Qdrant Point 补偿。"""
    try:
        _fail_indexing(document_id, chunk_ids, error)
    except Exception:
        logger.exception(
            "向量索引失败状态登记失败",
            extra={"document_id": document_id},
        )

    if vector_store is None or not point_ids:
        return
    try:
        vector_store.delete_points(list(point_ids))
    except Exception:
        logger.exception(
            "Qdrant 索引补偿删除失败",
            extra={
                "document_id": document_id,
                "point_count": len(point_ids),
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
