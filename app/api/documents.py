"""文档管理兼容 API。"""

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.schemas.chunking import BuildChunksResponse
from app.schemas.document import (
    DocumentProcessResponse,
    DocumentResponse,
    DocumentUploadFormData,
)
from app.schemas.vector_indexing import VectorIndexingResponse
from app.services.document_chunking_service import build_document_chunks
from app.services.document_processing_service import process_document
from app.services.document_upload_service import save_uploaded_document
from app.services.vector_indexing_service import index_document_vectors


router = APIRouter(prefix="/admin/documents", tags=["documents"])


def document_upload_form(
    title: str = Form(...),
    kb_id: int = Form(...),
    domain_code: str = Form(...),
    business_scene: Optional[str] = Form(None),
    risk_level: Literal["low", "medium", "high", "critical"] = Form("low"),
    effective_at: Optional[datetime] = Form(None),
    expired_at: Optional[datetime] = Form(None),
) -> DocumentUploadFormData:
    """将 multipart 表单字段组装为上传服务使用的元数据对象。"""
    return DocumentUploadFormData(
        title=title,
        kb_id=kb_id,
        domain_code=domain_code,
        business_scene=business_scene,
        risk_level=risk_level,
        effective_at=effective_at,
        expired_at=expired_at,
    )


@router.post(
    "/upload",
    response_model=DocumentResponse,
)
async def upload_document(
    file: UploadFile = File(...),
    meta: DocumentUploadFormData = Depends(document_upload_form),
):
    """接收原始文件并创建处于 uploaded 状态的文档记录。"""
    created_by_actor_code = "knowledge_operator_001"

    return await save_uploaded_document(
        file=file,
        meta=meta,
        created_by_actor_code=created_by_actor_code,
    )


@router.post(
    "/{document_id}/process",
    response_model=DocumentProcessResponse,
)
def trigger_document_processing(
    document_id: int,
):
    """触发指定文档的清洗或外部格式转换流程。"""
    return process_document(
        document_id=document_id,
    )


@router.post(
    "/{document_id}/build-chunks",
    response_model=BuildChunksResponse,
)
def trigger_build_chunks(
    document_id: int,
):
    """基于已清洗的文本重建父块和子块。"""
    return build_document_chunks(
        document_id=document_id,
    )


@router.post(
    "/{document_id}/index-vectors",
    response_model=VectorIndexingResponse,
)
def trigger_vector_indexing(
    document_id: int,
):
    """为尚未索引的子块生成向量并写入向量库。"""
    return index_document_vectors(
        document_id=document_id,
    )
