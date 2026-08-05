"""可靠消息应用层 DTO。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeEvent:
    event_id: str
    event_type: str
    payload: dict
