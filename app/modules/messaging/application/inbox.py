"""业务事务内使用的 Inbox 幂等辅助器。"""

from datetime import datetime
from uuid import uuid4

def record_inbox_once(
    uow,
    *,
    inbox_event_factory,
    consumer_name: str,
    event_id: str,
) -> bool:
    """在调用方业务 UoW 中登记；False 表示已处理。"""
    if uow.inbox.exists(consumer_name, event_id):
        return False
    uow.inbox.add(
        inbox_event_factory(
            inbox_id=f"inbox_{uuid4().hex}",
            consumer_name=consumer_name,
            event_id=event_id,
            processed_at=datetime.now(),
        )
    )
    return True
