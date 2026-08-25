"""Executor 取消时等待内部副作用执行真正静默的工具函数。

当 Task 执行超时或收到 asyncio.CancelledError 时，由于底层同步 Use Case（跑在线程池中）
无法被强制杀死，必须先使用 shield 等待底层操作完全退出（静默），然后再传播取消异常。
这能严格防止"旧执行仍在写入文件/数据库，而新的 Compensator 已经开始删除"引发的并发竞争与数据损坏。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar

ResultT = TypeVar("ResultT")


async def await_side_effect_quiescence(
    awaitable: Awaitable[ResultT],
) -> ResultT:
    """收到取消后先排空内部执行，避免补偿与旧副作用并发。

    Args:
        awaitable: 需要受保护执行的协程或 Future。

    Returns:
        ResultT: 内部 awaitable 执行成功后的返回结果。

    Raises:
        asyncio.CancelledError: 当外部发生取消且内部执行已完全静默排空后抛出。
        BaseException: 内部执行本身抛出的其他异常。
    """
    task = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # 持续 shield 等待 task 彻底完成，屏蔽多轮连续取消信号
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        # 消费异常避免 Unhandled Exception 报警
        if not task.cancelled():
            task.exception()
        raise
