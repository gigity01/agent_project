"""Messaging 领域层模块。

导出可靠消息相关的领域枚举定义，包括发件箱事件生命周期状态等。
"""

from app.modules.messaging.domain.enums import OutboxEventStatus

__all__ = ["OutboxEventStatus"]
