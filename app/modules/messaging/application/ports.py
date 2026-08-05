"""可靠消息发布端口。"""

from typing import Protocol


class MessagePublisherPort(Protocol):
    async def publish(
        self,
        *,
        event_id: str,
        event_type: str,
        payload: dict,
    ) -> None:
        ...
