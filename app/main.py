"""新版知识库管理 API 的 FastAPI 路由入口。"""

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
# 启动时输出已导入的 ORM 表，便于本地确认 Alembic/模型注册是否完整；
# 它不是数据库建表操作，也不应作为生产环境的审计日志来源。
print("REGISTERED TABLES:", list(Base.metadata.tables.keys()))

@app.post(
    "/api/admin/documents/upload",
    response_model=DocumentResponse,
)
async def upload_document(
    file: UploadFile = File(...),
    meta: DocumentUploadFormData = Depends(document_upload_form),
):
    """接收原始文件并创建处于 draft 状态的文档记录。"""
    created_by_actor_code = "knowledge_operator_001"

    return await save_uploaded_document(
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
):
    """触发指定文档的清洗或外部格式转换流程。

    成功后文档从 ``uploaded`` 进入 ``processed``，并产生后续切块所需的
    ``cleaned_uri``；切块与向量索引由独立端点触发，避免长任务相互耦合。
    """
    return process_document(
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
    """基于已清洗的文本重建父块和子块。

    该步骤会替换同一文档的旧块数据，必须在处理完成后调用，向量索引则在
    块数据落库后单独执行。
    """
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
    """为尚未索引的子块生成向量并写入向量库。

    只处理 ``pending`` 子块，因而重复调用可用于补偿失败或新增的索引任务。
    """
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
