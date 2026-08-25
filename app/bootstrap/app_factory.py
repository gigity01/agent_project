"""FastAPI 应用工厂模块。

职责说明：
- 提供 `create_app()` 工厂函数，创建并配置标准 FastAPI 应用实例。
- 预先调用 `load_all_models()` 完成全局 SQLAlchemy ORM 模型元数据注册。
- 绑定全局生命周期上下文管理器 (`lifespan`) 与领域应用层异常处理器。
- 挂载全局 API Router (`/api`)。
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.bootstrap.lifespan import lifespan
from app.infrastructure.database.model_registry import load_all_models
from app.modules.document.application.errors import DocumentApplicationError

# 确保在应用构建前所有领域 ORM 模型已导入并注册至 Base.metadata
load_all_models()


async def _document_application_error_handler(
    request: Request,
    exc: DocumentApplicationError,
) -> JSONResponse:
    """统一捕获 Document 领域应用层异常并转换为对应的 HTTP JSON 响应。

    参数:
        request: FastAPI HTTP 请求对象。
        exc: Document 领域应用层异常实例。

    返回:
        JSONResponse: 包含状态码与 `{"detail": exc.detail}` 的响应体。
    """
    del request
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


def create_app() -> FastAPI:
    """创建、配置并返回注册了完整路由与异常处理器的 FastAPI 实例。

    返回:
        FastAPI: 配置完成的应用实例。
    """
    application = FastAPI(
        title="AJ3Q Knowledge Admin API",
        lifespan=lifespan,
    )
    # 注册 Document 领域异常处理器
    application.add_exception_handler(
        DocumentApplicationError,
        _document_application_error_handler,
    )
    # 挂载统一 API Router
    application.include_router(api_router)
    return application
