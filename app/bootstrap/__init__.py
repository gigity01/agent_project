"""应用引导、依赖注入容器与生命周期管理包。

职责说明：
- `app_factory.py`: FastAPI 应用实例工厂函数与全局异常处理器注册。
- `container.py`: `AppContainer` 数据容器，集中持有全局共享的外部客户端、Agent 运行时与各领域 Use Case。
- `lifespan.py`: FastAPI 异步生命周期管理器，负责启动时客户端探测连接与依赖装配、停机时优雅释放资源。
- `dependencies.py`: FastAPI 依赖注入辅助函数（如 `get_container`）。
"""
