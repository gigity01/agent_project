"""跨模块共享的 FastAPI 容器依赖注入模块。

职责说明：
- 提供 FastAPI 依赖注入函数 `get_container`，从 `request.app.state.container` 中提取已初始化的 `AppContainer` 实例。
- 在应用未就绪或未初始化时抛出明确的运行时异常。
"""

from fastapi import Request

from app.bootstrap.container import AppContainer


def get_container(request: Request) -> AppContainer:
    """从 FastAPI Request 应用状态中获取全局唯一的 AppContainer 实例。

    参数:
        request: FastAPI HTTP 请求对象。

    返回:
        AppContainer: 全局应用依赖容器实例。

    异常:
        RuntimeError: 当应用容器尚未初始化或类型不匹配时抛出。
    """
    container = getattr(request.app.state, "container", None)
    if not isinstance(container, AppContainer):
        raise RuntimeError("应用容器尚未初始化")
    return container
