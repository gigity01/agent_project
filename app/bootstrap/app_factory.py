"""FastAPI 应用工厂。"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import app.modules.context.infrastructure.persistence.models
import app.modules.document.infrastructure.persistence.models.child_chunk
import app.modules.document.infrastructure.persistence.models.document
import app.modules.document.infrastructure.persistence.models.document_artifact
import app.modules.document.infrastructure.persistence.models.knowledge_base
import app.modules.document.infrastructure.persistence.models.parent_block
from app.api.router import api_router
from app.bootstrap.lifespan import lifespan
from app.modules.document.application.errors import DocumentApplicationError


async def _document_application_error_handler(
    request: Request,
    exc: DocumentApplicationError,
) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


def create_app() -> FastAPI:
    """创建并注册完整 API Router。"""
    application = FastAPI(
        title="AJ3Q Knowledge Admin API",
        lifespan=lifespan,
    )
    application.add_exception_handler(
        DocumentApplicationError,
        _document_application_error_handler,
    )
    application.include_router(api_router)
    return application
