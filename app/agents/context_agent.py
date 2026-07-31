"""Context Router 兼容导出。"""

from app.modules.context.infrastructure.llm.deepseek_router import (
    CONTEXT_AGENT_INSTRUCTIONS,
    CONTEXT_ROUTE_TOOL_NAME,
    DEFAULT_CONTEXT_AGENT_OUTPUT_ATTEMPTS,
    DeepSeekContextRouter,
)
from app.modules.context.infrastructure.llm.strict_schema_adapter import (
    ContextAgentOutputError,
    build_context_route_tool_schema,
)


ContextAgentRouter = DeepSeekContextRouter

__all__ = [
    "CONTEXT_AGENT_INSTRUCTIONS",
    "CONTEXT_ROUTE_TOOL_NAME",
    "DEFAULT_CONTEXT_AGENT_OUTPUT_ATTEMPTS",
    "ContextAgentOutputError",
    "ContextAgentRouter",
    "DeepSeekContextRouter",
    "build_context_route_tool_schema",
]
