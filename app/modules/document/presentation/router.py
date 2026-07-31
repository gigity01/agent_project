"""文档模块 HTTP Router。"""

from fastapi import APIRouter, Depends, File, UploadFile

from app.modules.document.application.use_cases.build_chunks import (
    build_document_chunks,
)
from app.modules.document.application.use_cases.index_vectors import (
    index_document_vectors,
)
from app.modules.document.application.use_cases.process_document import (
    process_document,
)
from app.modules.document.application.use_cases.upload_document import (
    save_uploaded_document,
)
from app.modules.document.presentation.dependencies import document_upload_form
from app.modules.document.presentation.schemas import (
    BuildChunksResponse,
    DocumentProcessResponse,
    DocumentResponse,
    DocumentUploadFormData,
    VectorIndexingResponse,
)


router = APIRouter(prefix="/admin/documents", tags=["documents"])


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
