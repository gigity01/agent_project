"""应用统一 API Router。"""

from fastapi import APIRouter

from app.modules.context.presentation.router import (
    legacy_router as context_legacy_router,
    router as context_router,
)
from app.modules.document.presentation.router import (
    artifact_router as document_artifacts_router,
    child_chunk_router,
    knowledge_base_router,
    parent_block_router,
    router as documents_router,
)


api_router = APIRouter(prefix="/api")
api_router.include_router(context_router)
api_router.include_router(context_legacy_router)
api_router.include_router(documents_router)
api_router.include_router(document_artifacts_router)
api_router.include_router(parent_block_router)
api_router.include_router(child_chunk_router)
api_router.include_router(knowledge_base_router)
