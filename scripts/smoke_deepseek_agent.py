"""验证 OpenAI Agents SDK 能通过 DeepSeek 执行最小 Agent。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


# 允许按文档直接执行 ``python scripts/smoke_deepseek_agent.py``。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents import Agent, Runner

from app.infrastructure.llm.deepseek.provider import (
    DeepSeekModelProvider,
    build_deepseek_run_config,
)


async def main() -> None:
    provider = DeepSeekModelProvider.create()

    try:
        agent = Agent(
            name="SDK Smoke Agent",
            instructions=(
                "你是 SDK 连通性测试 Agent。"
                "收到输入后只回复 SDK_OK，不要补充其他内容。"
            ),
        )

        result = await Runner.run(
            agent,
            input="执行连通性检查。",
            max_turns=1,
            run_config=build_deepseek_run_config(provider),
        )

        output = str(result.final_output).strip()

        if output != "SDK_OK":
            raise RuntimeError(f"Agent SDK 冒烟测试输出异常: {output!r}")

        print("DeepSeek Agents SDK smoke test: OK")

    finally:
        await provider.aclose()


if __name__ == "__main__":
    asyncio.run(main())
