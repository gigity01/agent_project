"""将已清洗文档持久化为父块和待索引子块。"""

from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.chunkers.base import ChunkBuildInput
from app.chunkers.common import md5_text
from app.chunkers.factory import get_chunker
from app.constants.document_status import DocumentStatus
from app.models.child_chunk import ChildChunk
from app.models.parent_block import ParentBlock
from app.repositories.child_chunk_repository import ChildChunkRepository
from app.repositories.document_artifact_repository import DocumentArtifactRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.parent_block_repository import ParentBlockRepository
from app.policies.document_source_policy import get_expected_process_output_type
from app.schemas.chunking import BuildChunksResponse


def generate_parent_code(doc_code: str, block_index: int) -> str:
    """为文档内的父块生成可追踪的业务编号。"""
    return f"PB_{doc_code}_{block_index:04d}_{uuid4().hex[:6].upper()}"


def generate_chunk_code(doc_code: str, parent_index: int, chunk_index: int) -> str:
    """为父块内的子块生成可追踪的业务编号。"""
    return f"CK_{doc_code}_{parent_index:04d}_{chunk_index:04d}_{uuid4().hex[:6].upper()}"


def build_document_chunks(
    db: Session,
    document_id: int,
) -> BuildChunksResponse:
    """根据清洗文本重建当前文档的父块和子块。

    同一文档重复构建时，会在同一事务中先删除旧子块，再删除旧父块。
    """
    document_repo = DocumentRepository(db)
    artifact_repo = DocumentArtifactRepository(db)
    parent_repo = ParentBlockRepository(db)
    child_repo = ChildChunkRepository(db)

    document = document_repo.get_by_id(document_id)

    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    if document.status not in {
        DocumentStatus.PROCESSED.value,
        DocumentStatus.CHUNKED.value,
    }:
        raise HTTPException(
            status_code=400,
            detail=f"当前文档状态不允许切块: {document.status}",
        )

    cleaned_artifact = artifact_repo.get_latest_active(
        document_id=document.id,
        artifact_type="cleaned_text",
        artifact_role="process_output",
    )

    if cleaned_artifact is not None:
        cleaned_path = Path(cleaned_artifact.artifact_uri)
        chunk_source_type = cleaned_artifact.artifact_format
        process_metadata = cleaned_artifact.metadata_json or {}
    else:
        # 兼容 Artifact 表接入前已经处理完成、仅保留 cleaned_uri 的旧记录。
        if document.cleaned_uri is None:
            raise HTTPException(status_code=400, detail="文档尚未处理")

        cleaned_path = Path(document.cleaned_uri)
        chunk_source_type = get_expected_process_output_type(
            document.source_type
        )
        process_metadata = {}

    if not cleaned_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"cleaned 文件不存在: {cleaned_path}",
        )

    if not cleaned_path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"cleaned 路径不是有效文件: {cleaned_path}",
        )

    chunker = get_chunker(chunk_source_type)

    try:
        result = chunker.build(
            ChunkBuildInput(
                cleaned_path=cleaned_path,
                document_title=document.title,
                business_scene=document.business_scene,
                process_metadata=process_metadata,
            )
        )

        if not result.parents:
            raise HTTPException(status_code=400, detail="未生成任何 parent block")

        # 重建策略：同一个 doc 重新 build 时，先删旧 child，再删旧 parent。
        child_repo.delete_by_doc_id(document.id)
        parent_repo.delete_by_doc_id(document.id)

        parent_count = 0
        child_count = 0

        for parent_data in result.parents:
            parent_block = ParentBlock(
                parent_code=generate_parent_code(
                    doc_code=document.doc_code,
                    block_index=parent_data.block_index,
                ),
                kb_id=document.kb_id,
                doc_id=document.id,
                domain_code=document.domain_code,
                business_scene=document.business_scene,
                block_type=parent_data.block_type,
                title=parent_data.title,
                section_path=parent_data.section_path,
                content=parent_data.content,
                content_hash=md5_text(parent_data.content),
                block_index=parent_data.block_index,
                semantic_group_index=parent_data.semantic_group_index,
                segment_index=parent_data.segment_index,
                status="active",
                version=document.version,
            )

            saved_parent = parent_repo.create(parent_block)
            parent_count += 1

            children = result.children_by_parent_index.get(
                parent_data.block_index,
                [],
            )

            for child_data in children:
                child_chunk = ChildChunk(
                    chunk_code=generate_chunk_code(
                        doc_code=document.doc_code,
                        parent_index=parent_data.block_index,
                        chunk_index=child_data.chunk_index,
                    ),
                    parent_id=saved_parent.id,
                    doc_id=document.id,
                    kb_id=document.kb_id,
                    domain_code=document.domain_code,
                    business_scene=document.business_scene,
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
                    version=document.version,
                    indexed_at=None,
                )

                child_repo.create(child_chunk)
                child_count += 1

        document.status = DocumentStatus.CHUNKED.value
        db.commit()

        return BuildChunksResponse(
            document_id=document.id,
            doc_code=document.doc_code,
            source_type=document.source_type,
            parent_count=parent_count,
            child_count=child_count,
            status="success",
        )

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"构建 chunks 失败: {str(e)}",
        )
