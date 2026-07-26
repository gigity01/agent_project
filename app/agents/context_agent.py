"""只负责上下文关联判断的 Context Agent。"""

from __future__ import annotations

from agents import Agent, Runner

from app.agents.deepseek_provider import (
    DeepSeekModelProvider,
    build_deepseek_run_config,
)
from app.schemas.context import (
    ContextAgentInput,
    ContextRouteDecision,
)


CONTEXT_AGENT_INSTRUCTIONS = """
你是上下文管理和消息路由 Agent。

你的唯一职责是判断当前完整用户输入与哪些已有上下文链相关，
以及是否包含与所有已有链都无关的新上下文。

规则：

1. 用户输入可以同时关联一条或多条已有链。
2. 不得拆分、改写或摘要当前用户输入。
3. 明确关联多条链时，返回全部相关 chain_id。
4. 与所有已有链无关时，创建新链。
5. 同时包含已有上下文和新上下文时，返回已有 chain_id，
   并标记需要创建新链。
6. 存在关联但无法判断具体归属时，选择 last_active_at 最新的链。
7. 不得生成计划、任务、操作、权限或执行建议。
8. 不得修改链内容、资源或时间戳。
9. 只提交结构化路由结果。
10. resource_queue 按从旧到新排列，越靠近队尾表示最近越活跃；
    队列只用于判断上下文关联，不得据此生成业务操作。

route_mode 与字段必须满足：

- single_match：恰好选择一条已有链，不创建新链。
- multi_match：选择至少两条已有链，不创建新链。
- new_chain：不选择已有链，创建新链。
- existing_and_new：选择至少一条已有链，同时创建新链。
- fallback_latest：恰好选择 last_active_at 最新的一条已有链，不创建新链。

reason_summary 只能简要说明上下文关联依据，不得包含后续业务计划或执行建议。
""".strip()


class ContextAgentRouter:
    """通过 OpenAI Agents SDK 调用 DeepSeek 并返回结构化路由决定。"""

    def __init__(self, provider: DeepSeekModelProvider) -> None:
        self._run_config = build_deepseek_run_config(provider)
        self._agent = Agent(
            name="Context Agent",
            instructions=CONTEXT_AGENT_INSTRUCTIONS,
            output_type=ContextRouteDecision,
        )

    async def route(
        self,
        agent_input: ContextAgentInput,
    ) -> ContextRouteDecision:
        result = await Runner.run(
            self._agent,
            input=agent_input.model_dump_json(indent=2),
            max_turns=1,
            run_config=self._run_config,
        )
        if isinstance(result.final_output, ContextRouteDecision):
            return result.final_output
        return ContextRouteDecision.model_validate(result.final_output)
