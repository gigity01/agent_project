"""FastAPI 应用工厂。"""

from fastapi import FastAPI

import app.models
from app.api.router import api_router
from app.bootstrap.lifespan import lifespan


def create_app() -> FastAPI:
    """创建并注册完整 API Router。"""
    application = FastAPI(
        title="AJ3Q Knowledge Admin API",
        lifespan=lifespan,
    )
    application.include_router(api_router)
    return application
