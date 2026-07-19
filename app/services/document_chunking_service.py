"""以短事务编排文档切块任务的领取、执行与结果登记。"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from app.chunkers.base import (
    ChildChunkData,
    ChunkBuildInput,
    ChunkBuildResult,
    ParentBlockData,
)
from app.chunkers.common import md5_text
from app.chunkers.factory import get_chunker
from app.constants.document_lifecycle_status import DocumentLifecycleStatus
from app.constants.document_status import DocumentStatus
from app.constants.document_storage_status import DocumentStorageStatus
from app.db.uow import SQLAlchemyUnitOfWork
from app.models.child_chunk import ChildChunk
from app.models.parent_block import ParentBlock
from app.policies.document_source_policy import get_expected_process_output_type
from app.schemas.chunking import BuildChunksResponse


CHUNKABLE_LIFECYCLE_STATUSES = frozenset(
    {
        DocumentLifecycleStatus.ACTIVE.value,
        DocumentLifecycleStatus.SCHEDULED.value,
    }
)


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


def build_document_chunks(document_id: int) -> BuildChunksResponse:
    """领取切块任务后在事务外计算，并以独立短事务登记结果。"""
    context = _claim_chunking(document_id)

    try:
        execution_result = _execute_chunking(context)
        return _complete_chunking(execution_result)
    except ChunkingAbortedError as exc:
        _fail_chunking(document_id, exc)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except HTTPException as exc:
        _fail_chunking(document_id, exc)
        raise
    except Exception as exc:
        _fail_chunking(document_id, exc)
        raise HTTPException(
            status_code=500,
            detail="构建 chunks 失败，请稍后重试或联系管理员",
        ) from exc


def _claim_chunking(document_id: int) -> ChunkingContext:
    """以行锁领取切块权，并立即提交 chunking 状态。"""
    with SQLAlchemyUnitOfWork() as uow:
        document = uow.documents.get_by_id_for_update(document_id)

        if document is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        if document.status not in {
            DocumentStatus.PROCESSED.value,
            DocumentStatus.FAILED.value,
        }:
            raise HTTPException(
                status_code=409,
                detail=f"当前文档状态不允许切块: {document.status}",
            )
        if document.lifecycle_status not in CHUNKABLE_LIFECYCLE_STATUSES:
            raise HTTPException(status_code=409, detail="失效文档不能切块")
        if document.storage_status != DocumentStorageStatus.ACTIVE.value:
            raise HTTPException(status_code=409, detail="文档不在活跃存储区")

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
                raise HTTPException(status_code=400, detail="文档尚未处理")
            cleaned_path = Path(document.cleaned_uri)
            chunk_source_type = get_expected_process_output_type(
                document.source_type
            )
            process_metadata = {}

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
        )
        document.status = DocumentStatus.CHUNKING.value
        uow.flush()
        uow.commit()

    return context


def _execute_chunking(
    context: ChunkingContext,
) -> ChunkingExecutionResult:
    """在数据库事务外读取 cleaned 文件并生成父子块 DTO。"""
    if not context.cleaned_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"cleaned 文件不存在: {context.cleaned_path}",
        )
    if not context.cleaned_path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"cleaned 路径不是有效文件: {context.cleaned_path}",
        )

    chunker = get_chunker(context.chunk_source_type)
    chunks = chunker.build(
        ChunkBuildInput(
            cleaned_path=context.cleaned_path,
            document_title=context.document_title,
            business_scene=context.business_scene,
            process_metadata=context.process_metadata,
        )
    )
    if not chunks.parents:
        raise HTTPException(status_code=400, detail="未生成任何 parent block")

    return ChunkingExecutionResult(context=context, chunks=chunks)


def _complete_chunking(
    result: ChunkingExecutionResult,
) -> BuildChunksResponse:
    """在短事务中复核状态、替换父子块并推进到 chunked。"""
    context = result.context
    with SQLAlchemyUnitOfWork() as uow:
        document = uow.documents.get_by_id_for_update(context.document_id)

        if document is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        if document.status != DocumentStatus.CHUNKING.value:
            raise HTTPException(
                status_code=409,
                detail=f"文档切块状态已经变化: {document.status}",
            )
        if document.lifecycle_status not in CHUNKABLE_LIFECYCLE_STATUSES:
            raise ChunkingAbortedError("文档切块期间已经失效")
        if document.storage_status != DocumentStorageStatus.ACTIVE.value:
            raise ChunkingAbortedError("文档已进入归档流程")

        # 在同一事务中先清旧 child、再清旧 parent，随后批量写入新块。
        uow.child_chunks.delete_by_doc_id(document.id)
        uow.parent_blocks.delete_by_doc_id(document.id)

        parent_blocks = [
            _build_parent_block(context, parent_data)
            for parent_data in result.chunks.parents
        ]
        saved_parents = uow.parent_blocks.create_many(parent_blocks)
        parents_by_block_index = {
            parent.block_index: parent for parent in saved_parents
        }

        child_chunks: list[ChildChunk] = []
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
                    )
                )
        uow.child_chunks.create_many(child_chunks)

        document.status = DocumentStatus.CHUNKED.value
        uow.flush()
        response = BuildChunksResponse(
            document_id=document.id,
            doc_code=document.doc_code,
            source_type=document.source_type,
            parent_count=len(parent_blocks),
            child_count=len(child_chunks),
            status="success",
        )
        uow.commit()

    return response


def _fail_chunking(document_id: int, error: Exception) -> None:
    """仅在任务仍为 chunking 时，以独立短事务标记切块失败。"""
    del error
    with SQLAlchemyUnitOfWork() as uow:
        document = uow.documents.get_by_id_for_update(document_id)
        if document is None:
            return
        if document.status == DocumentStatus.CHUNKING.value:
            document.status = DocumentStatus.FAILED.value
            uow.flush()
            uow.commit()


def _build_parent_block(
    context: ChunkingContext,
    parent_data: ParentBlockData,
) -> ParentBlock:
    """把事务外父块 DTO 转换为待持久化 ORM 对象。"""
    return ParentBlock(
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
) -> ChildChunk:
    """把事务外子块 DTO 转换为待持久化 ORM 对象。"""
    return ChildChunk(
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
