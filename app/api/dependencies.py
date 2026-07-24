"""FastAPI 请求依赖。"""

from fastapi import Request

from app.agents.runtime import AgentRuntime


def get_agent_runtime(request: Request) -> AgentRuntime:
    """获取应用生命周期内共享的 Agent 运行时。"""
    runtime = getattr(request.app.state, "agent_runtime", None)

    if not isinstance(runtime, AgentRuntime):
        raise RuntimeError("AgentRuntime 尚未初始化")

    return runtime
