from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.parent_block import ParentBlock
from app.models.child_chunk import ChildChunk
from app.repositories.document_repository import DocumentRepository
from app.repositories.parent_block_repository import ParentBlockRepository
from app.repositories.child_chunk_repository import ChildChunkRepository
from app.chunkers.factory import get_chunker
from app.chunkers.common import md5_text
from app.schemas.chunking import BuildChunksResponse


def generate_parent_code(doc_code: str, block_index: int) -> str:
    return f"PB_{doc_code}_{block_index:04d}_{uuid4().hex[:6].upper()}"


def generate_chunk_code(doc_code: str, parent_index: int, chunk_index: int) -> str:
    return f"CK_{doc_code}_{parent_index:04d}_{chunk_index:04d}_{uuid4().hex[:6].upper()}"


def build_document_chunks(
    db: Session,
    document_id: int,
) -> BuildChunksResponse:
    document_repo = DocumentRepository(db)
    parent_repo = ParentBlockRepository(db)
    child_repo = ChildChunkRepository(db)

    document = document_repo.get_by_id(document_id)

    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    if document.cleaned_uri is None:
        raise HTTPException(status_code=400, detail="文档尚未处理，没有 cleaned_uri")

    if document.status != "active":
        raise HTTPException(
            status_code=400,
            detail=f"当前文档状态不允许切块: {document.status}",
        )

    cleaned_path = Path(document.cleaned_uri)

    if not cleaned_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"cleaned 文件不存在: {document.cleaned_uri}",
        )

    text = cleaned_path.read_text(encoding="utf-8", errors="ignore")

    chunker = get_chunker(document.source_type)

    result = chunker.build(
        text=text,
        document_title=document.title,
        business_scene=document.business_scene,
    )

    if not result.parents:
        raise HTTPException(status_code=400, detail="未生成任何 parent block")

    try:
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

        db.commit()

        return BuildChunksResponse(
            document_id=document.id,
            doc_code=document.doc_code,
            source_type=document.source_type,
            parent_count=parent_count,
            child_count=child_count,
            status="success",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"构建 chunks 失败: {str(e)}",
        )