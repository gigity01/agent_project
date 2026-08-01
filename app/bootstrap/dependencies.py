"""跨模块共享的 FastAPI 容器依赖。"""

from fastapi import Request

from app.bootstrap.container import AppContainer


def get_container(request: Request) -> AppContainer:
    """获取应用生命周期内装配完成的统一容器。"""
    container = getattr(request.app.state, "container", None)
    if not isinstance(container, AppContainer):
        raise RuntimeError("应用容器尚未初始化")
    return container
