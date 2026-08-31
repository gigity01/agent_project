"""Context Chain 的 SQLAlchemy ORM 定义。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base


class ContextChain(Base):
    """保存上下文链身份、资源版本与业务活跃时间的 ORM 实体。

    字段说明：
    - chain_id: 上下文链唯一标识（主键）。
    - conversation_id: 所属会话 ID。
    - resources: 旧版兼容 JSON 字段，不再作为正式资源事实或由完成流程整包维护。
    - resource_version: 资源状态单调递增版本号，用于控制与 Redis 缓存的一致性。
    - last_active_at: 最近活跃时间戳，用于链活跃度排序。
    - archived: 是否已归档。
    - created_at: 创建时间。
    - nodes: 关联的 ContextChainNode 节点列表（按 sequence 升序排列）。
    """

    __tablename__ = "context_chains"

    chain_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # 兼容旧数据；正式资源事实保存在资源状态表和事件表中。
    resources: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    resource_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_active_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    nodes = relationship(
        "ContextChainNode",
        back_populates="chain",
        cascade="all, delete-orphan",
        order_by="ContextChainNode.sequence",
    )


Index(
    "idx_context_chains_conversation_active",
    ContextChain.conversation_id,
    ContextChain.archived,
    ContextChain.last_active_at,
)
