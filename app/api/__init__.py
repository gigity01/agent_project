"""FastAPI 传输层与全局路由聚合包。

职责说明：
- 汇聚系统各业务领域（Conversation、Context、Document 等）的 HTTP API 端点路由。
- 暴露统一的 `/api` 前缀路由对象 `api_router` 供应用工厂挂载。
"""
