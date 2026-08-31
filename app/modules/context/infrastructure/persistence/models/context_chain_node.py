"""Context Chain Node 的 SQLAlchemy ORM 定义。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.infrastructure.database.base import Base


class ContextChainNode(Base):
    """引用唯一 Turn，并保存该 Turn 在当前链中的关联信息与序号的 ORM 实体。

    约束与设计：
    - (chain_id, sequence) 联合唯一索引：确保单链内节点序号连续且唯一递增。
    - (chain_id, turn_id) 联合唯一索引：确保同一 Turn 在同一 Chain 中只存在一个节点。
    - 仅保存关联关系（related_task_ids, related_resource_refs）与 Turn 外键，不冗余复制 Turn 文本。
    """

    __tablename__ = "context_chain_nodes"
    __table_args__ = (
        UniqueConstraint(
            "chain_id",
            "sequence",
            name="uq_context_chain_nodes_chain_sequence",
        ),
        UniqueConstraint(
            "chain_id",
            "turn_id",
            name="uq_context_chain_nodes_chain_turn",
        ),
    )

    node_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    chain_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("context_chains.chain_id"),
        nullable=False,
    )
    turn_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("conversation_turns.turn_id"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    related_task_ids: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    related_resource_refs: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    chain = relationship("ContextChain", back_populates="nodes")
    turn = relationship("ConversationTurn", back_populates="nodes")


Index(
    "idx_context_chain_nodes_turn",
    ContextChainNode.turn_id,
)
