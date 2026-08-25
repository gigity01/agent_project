"""FastAPI 应用入口模块。

职责说明：
- 作为 Web API 服务的顶层执行入口与 ASGI 应用定义点。
- 通过应用工厂模式创建 FastAPI 实例，挂载各业务模块路由与统一生命周期管理器 (Lifespan)。
- 提供本地开发调试运行函数 `main()`，支持通过 Uvicorn 启动热重载开发服务器。

架构约束：
- 仅承载 HTTP API 流量编排与同步/异步 Plan 提交，不直接消费异步 Task 队列（由独立的 Runtime Worker 进程消费）。
- 依赖注入由 Bootstrap 容器组装，严格遵循分层依赖规范。
"""

import uvicorn

from app.bootstrap.app_factory import create_app

# 初始化全局 FastAPI 应用实例
app = create_app()


def main() -> None:
    """从项目根目录启动本地 Uvicorn 开发服务器。

    启动配置：
    - 绑定本地环回地址 127.0.0.1，端口 8000。
    - 开启代码热重载 (reload=True)，适用于本地开发环境。

    注意：
    - 生产环境建议通过外部进程管理器 (如 Gunicorn/Uvicorn CLI) 运行 `app.main:app`。
    """
    # 启动 ASGI Web 服务器
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
