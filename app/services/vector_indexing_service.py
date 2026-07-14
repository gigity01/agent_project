"""生成子块向量并将其写入 Qdrant 的业务编排服务。"""

from fastapi import HTTPException
from qdrant_client.models import PointStruct
from sqlalchemy.orm import Session

from app.repositories.document_repository import DocumentRepository
from app.repositories.child_chunk_repository import ChildChunkRepository
from app.services.embedding_service import EmbeddingService
from app.vectorstores.qdrant_store import QdrantVectorStore
from app.schemas.vector_indexing import VectorIndexingResponse
from app.app_config.settings import EMBEDDING_VECTOR_SIZE


def index_document_vectors(
    db: Session,
    document_id: int,
) -> VectorIndexingResponse:
    """索引指定文档中所有待处理子块。

    调用外部服务前先提交 indexing 状态；失败时尽力将本批子块标记为 failed。
    """
    document_repo = DocumentRepository(db)
    chunk_repo = ChildChunkRepository(db)

    document = document_repo.get_by_id(document_id)

    if document is None:
        raise HTTPException(status_code=404, detail="文档不存在")

    chunks = chunk_repo.list_pending_by_doc_id(document_id)

    if not chunks:
        return VectorIndexingResponse(
            document_id=document_id,
            total_chunks=0,
            indexed_chunks=0,
            failed_chunks=0,
            status="no_pending_chunks",
        )

    chunk_ids = [chunk.id for chunk in chunks]

    try:
        # 外部 Embedding/Qdrant 调用无法加入数据库事务，先持久化 indexing 状态，
        # 失败时再尽力转为 failed，供后续补偿任务识别。
        chunk_repo.mark_indexing(chunks)
        db.commit()

        texts = [chunk.embedding_text for chunk in chunks]

        embedding_service = EmbeddingService()
        vectors = embedding_service.embed_texts(texts)

        if len(vectors) != len(chunks):
            raise RuntimeError(
                f"Embedding 返回数量不一致: chunks={len(chunks)}, vectors={len(vectors)}"
            )

        for vector in vectors:
            if len(vector) != EMBEDDING_VECTOR_SIZE:
                raise RuntimeError(
                    f"Embedding 维度不一致: expected={EMBEDDING_VECTOR_SIZE}, actual={len(vector)}"
                )

        points: list[PointStruct] = []

        # Qdrant point id 与关系库子块主键一一对应，便于跨存储定位和幂等 upsert。
        for chunk, vector in zip(chunks, vectors):
            point_id = int(chunk.id)

            payload = {
                "chunk_id": chunk.id,
                "chunk_code": chunk.chunk_code,
                "parent_id": chunk.parent_id,
                "section_path": chunk.section_path,
                "source_row_index": chunk.source_row_index,
                "doc_id": chunk.doc_id,
                "kb_id": chunk.kb_id,
                "domain_code": chunk.domain_code,
                "business_scene": chunk.business_scene,
                "source_type": document.source_type,
                "title": document.title,
                "original_filename": document.original_filename,
            }

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            )

        vector_store = QdrantVectorStore()
        vector_store.upsert_points(points)

        for chunk in chunks:
            chunk_repo.mark_indexed(
                chunk=chunk,
                qdrant_point_id=str(chunk.id),
            )

        db.commit()

        return VectorIndexingResponse(
            document_id=document_id,
            total_chunks=len(chunks),
            indexed_chunks=len(chunks),
            failed_chunks=0,
            status="success",
        )

    except Exception as e:
        # 这里的失败标记是补偿动作；若补偿本身失败，保留原异常并让运维从日志中
        # 发现仍处于 indexing 的块。
        db.rollback()

        try:
            chunk_repo.mark_failed_by_ids(chunk_ids)
            db.commit()
        except Exception:
            db.rollback()

        raise HTTPException(
            status_code=500,
            detail=f"向量索引失败: {str(e)}",
        )
