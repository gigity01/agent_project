import app.models
from datetime import datetime
from typing import Optional, Literal
from app.db.session import Base
from fastapi import FastAPI, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.document import (
    DocumentUploadFormData,
    DocumentResponse,
    DocumentProcessResponse,
)
from app.services.document_upload_service import save_uploaded_document
from app.services.document_processing_service import process_document

from app.schemas.chunking import BuildChunksResponse
from app.services.document_chunking_service import build_document_chunks

from app.schemas.vector_indexing import VectorIndexingResponse
from app.services.vector_indexing_service import index_document_vectors


app = FastAPI(
    title="AJ3Q Knowledge Admin API",
)


def document_upload_form(
    title: str = Form(...),
    kb_id: int = Form(...),
    domain_code: str = Form(...),
    business_scene: Optional[str] = Form(None),
    risk_level: Literal["low", "medium", "high", "critical"] = Form("low"),
    effective_at: Optional[datetime] = Form(None),
    expired_at: Optional[datetime] = Form(None),
) -> DocumentUploadFormData:
    return DocumentUploadFormData(
        title=title,
        kb_id=kb_id,
        domain_code=domain_code,
        business_scene=business_scene,
        risk_level=risk_level,
        effective_at=effective_at,
        expired_at=expired_at,
    )
print("REGISTERED TABLES:", list(Base.metadata.tables.keys()))

@app.post(
    "/api/admin/documents/upload",
    response_model=DocumentResponse,
)
async def upload_document(
    file: UploadFile = File(...),
    meta: DocumentUploadFormData = Depends(document_upload_form),
    db: Session = Depends(get_db),
):
    created_by_actor_code = "knowledge_operator_001"

    return await save_uploaded_document(
        db=db,
        file=file,
        meta=meta,
        created_by_actor_code=created_by_actor_code,
    )


@app.post(
    "/api/admin/documents/{document_id}/process",
    response_model=DocumentProcessResponse,
)
def trigger_document_processing(
    document_id: int,
    db: Session = Depends(get_db),
):
    return process_document(
        db=db,
        document_id=document_id,
    )

@app.post(
    "/api/admin/documents/{document_id}/build-chunks",
    response_model=BuildChunksResponse,
)
def trigger_build_chunks(
    document_id: int,
    db: Session = Depends(get_db),
):
    return build_document_chunks(
        db=db,
        document_id=document_id,
    )

@app.post(
    "/api/admin/documents/{document_id}/index-vectors",
    response_model=VectorIndexingResponse
)
def trigger_vector_indexing(
    document_id: int,
    db: Session = Depends(get_db),
):
    return index_document_vectors(
        db=db,
        document_id=document_id,
    )



# 主文件末尾追加
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        reload=True,
        host="127.0.0.1",
        port=8000
    )