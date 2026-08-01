"""FastAPI 应用工厂。"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.bootstrap.lifespan import lifespan
from app.infrastructure.database.model_registry import load_all_models
from app.modules.document.application.errors import DocumentApplicationError


load_all_models()


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
