"""Context Chain 的 SQLAlchemy ORM 定义。"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base


class ContextChain(Base):
    """保存上下文链身份、资源版本与业务活跃时间。"""

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
