"""可靠消息发布端口协议定义。

定义发件箱发布器向底层消息传输介质投递消息的标准接口。
"""

from typing import Protocol


class MessagePublisherPort(Protocol):
    """消息发布端口协议。

    负责将结构化事件投递至具体传输通道（如 Redis Streams、RabbitMQ 等）。
    """

    async def publish(
        self,
        *,
        event_id: str,
        event_type: str,
        payload: dict,
    ) -> None:
        """异步发布单个事件到传输媒介。

        Args:
            event_id: 事件全局唯一标识符。
            event_type: 事件类型名称。
            payload: 事件携带的参数载荷字典。

        Raises:
            Exception: 当底层网络异常或中间件投递失败时抛出。
        """
        ...
