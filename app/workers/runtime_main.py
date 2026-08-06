"""Outbox Publisher 与 Runtime Event Consumer 的独立进程入口。"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
from uuid import uuid4

from app.bootstrap.lifespan import build_container
from app.modules.messaging.infrastructure.redis_streams import (
    RedisStreamWorker,
)


LOGGER = logging.getLogger(__name__)

OUTBOX_IDLE_SECONDS = 0.5
INITIAL_RETRY_SECONDS = 1.0
MAX_RETRY_SECONDS = 30.0
STREAM_BLOCK_MILLISECONDS = 5_000


def build_consumer_name() -> str:
    """生成跨主机、进程和进程重启均唯一的 Redis consumer_name。"""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:12]}"


async def _wait_or_stop(
    stop_event: asyncio.Event,
    timeout_seconds: float,
) -> bool:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=timeout_seconds)
    except TimeoutError:
        return False
    return True


async def run_outbox_loop(
    publisher,
    *,
    stop_event: asyncio.Event,
) -> None:
    """持续发布可用 Outbox；循环级异常按指数退避重试。"""
    retry_seconds = INITIAL_RETRY_SECONDS
    while not stop_event.is_set():
        try:
            published = await publisher.publish_batch()
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception(
                "Outbox Publisher 循环异常，%.1f 秒后重试",
                retry_seconds,
            )
            if await _wait_or_stop(stop_event, retry_seconds):
                return
            retry_seconds = min(retry_seconds * 2, MAX_RETRY_SECONDS)
            continue

        retry_seconds = INITIAL_RETRY_SECONDS
        if published == 0 and await _wait_or_stop(
            stop_event,
            OUTBOX_IDLE_SECONDS,
        ):
            return


async def run_stream_loop(
    worker: RedisStreamWorker,
    *,
    stop_event: asyncio.Event,
) -> None:
    """持续消费 Runtime Event；失败消息不 ACK，并在退避后重试。"""
    retry_seconds = INITIAL_RETRY_SECONDS
    while not stop_event.is_set():
        try:
            await worker.run_once(
                block_milliseconds=STREAM_BLOCK_MILLISECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception(
                "Runtime Stream 循环异常，%.1f 秒后重试",
                retry_seconds,
            )
            if await _wait_or_stop(stop_event, retry_seconds):
                return
            retry_seconds = min(retry_seconds * 2, MAX_RETRY_SECONDS)
            continue

        retry_seconds = INITIAL_RETRY_SECONDS


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop_event.set)


async def run_worker() -> None:
    """装配并运行独立 Worker，收到退出信号后统一释放客户端。"""
    container = await build_container()
    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)
    redis_worker = RedisStreamWorker(
        container.redis_client,
        dispatcher=container.runtime_event_dispatcher,
        consumer_name=build_consumer_name(),
    )
    tasks = [
        asyncio.create_task(
            run_outbox_loop(
                container.outbox_publisher,
                stop_event=stop_event,
            ),
            name="outbox-publisher-loop",
        ),
        asyncio.create_task(
            run_stream_loop(redis_worker, stop_event=stop_event),
            name="runtime-stream-loop",
        ),
    ]

    try:
        await stop_event.wait()
    finally:
        stop_event.set()
        try:
            await asyncio.gather(*tasks)
        finally:
            await container.aclose()


def main() -> None:
    """使用 ``uv run python -m app.workers.runtime_main`` 启动。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
