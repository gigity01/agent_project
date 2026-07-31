"""应用统一 API Router。"""

from fastapi import APIRouter

from app.api.context import router as context_router
from app.api.conversations import router as conversations_router
from app.api.documents import router as documents_router


api_router = APIRouter(prefix="/api")
api_router.include_router(conversations_router)
api_router.include_router(context_router)
api_router.include_router(documents_router)
