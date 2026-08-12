"""Executor 取消时等待内部副作用执行真正静默。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar


ResultT = TypeVar("ResultT")


async def await_side_effect_quiescence(
    awaitable: Awaitable[ResultT],
) -> ResultT:
    """收到取消后先排空内部执行，避免补偿与旧副作用并发。"""
    task = asyncio.ensure_future(awaitable)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        if not task.cancelled():
            task.exception()
        raise
