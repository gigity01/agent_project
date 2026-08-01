"""文档模块 HTTP Router。"""

from fastapi import APIRouter, Depends, File, UploadFile

from app.modules.document.application.use_cases.build_chunks import (
    BuildChunksUseCase,
)
from app.modules.document.application.use_cases.index_vectors import (
    IndexVectorsUseCase,
)
from app.modules.document.application.use_cases.process_document import (
    ProcessDocumentUseCase,
)
from app.modules.document.application.use_cases.upload_document import (
    UploadDocumentUseCase,
)
from app.modules.document.presentation.dependencies import (
    document_upload_form,
    get_build_chunks_use_case,
    get_index_vectors_use_case,
    get_process_document_use_case,
    get_upload_document_use_case,
)
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
    use_case: UploadDocumentUseCase = Depends(
        get_upload_document_use_case
    ),
):
    """接收原始文件并创建处于 uploaded 状态的文档记录。"""
    return await use_case.execute(
        file=file,
        meta=meta,
    )


@router.post(
    "/{document_id}/process",
    response_model=DocumentProcessResponse,
)
def trigger_document_processing(
    document_id: int,
    use_case: ProcessDocumentUseCase = Depends(
        get_process_document_use_case
    ),
):
    """触发指定文档的清洗或外部格式转换流程。"""
    return use_case.execute(document_id)


@router.post(
    "/{document_id}/build-chunks",
    response_model=BuildChunksResponse,
)
def trigger_build_chunks(
    document_id: int,
    use_case: BuildChunksUseCase = Depends(get_build_chunks_use_case),
):
    """基于已清洗的文本重建父块和子块。"""
    return use_case.execute(document_id)


@router.post(
    "/{document_id}/index-vectors",
    response_model=VectorIndexingResponse,
)
def trigger_vector_indexing(
    document_id: int,
    use_case: IndexVectorsUseCase = Depends(get_index_vectors_use_case),
):
    """为尚未索引的子块生成向量并写入向量库。"""
    return use_case.execute(document_id)
