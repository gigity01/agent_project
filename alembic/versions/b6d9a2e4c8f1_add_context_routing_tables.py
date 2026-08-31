"""创建 Context 子系统核心数据表：会话轮次、上下文链、链节点与路由决策。

业务背景与设计规范：
1. `conversation_turns`：记录单轮用户输入、任务 ID 列表、执行结果摘要及轮次生命周期状态。
2. `context_chains`：维护对话中的上下文链，包含链关联的资源快照、最后活跃时间（last_active_at）和归档状态。
3. `context_chain_nodes`：上下文链与会话轮次的多对多关联节点表，通过 `uq_context_chain_nodes_chain_sequence` 保证链内顺序唯一，
   通过 `uq_context_chain_nodes_chain_turn` 保证同一轮次在单链内只挂载一次。
4. `context_route_decisions`：记录 Context Agent 的路由决策（单链匹配/多链匹配/新链创建/同时关联新旧链/回退最新未归档链）。

Revision ID: b6d9a2e4c8f1
Revises: e7b3c2d4a9f1
Create Date: 2026-07-25 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b6d9a2e4c8f1"
down_revision: Union[str, Sequence[str], None] = "e7b3c2d4a9f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 conversation_turns、context_chains、context_chain_nodes 和 context_route_decisions 四张持久化表及其外键与索引约束。"""
    op.create_table(
        "conversation_turns",
        sa.Column("turn_id", sa.String(length=100), nullable=False),
        sa.Column("conversation_id", sa.String(length=100), nullable=False),
        sa.Column("user_input", sa.Text(), nullable=False),
        sa.Column("assistant_content", sa.Text(), nullable=True),
        sa.Column("assistant_compact", sa.Text(), nullable=True),
        sa.Column("task_ids", sa.JSON(), nullable=False),
        sa.Column("task_result_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("turn_id"),
    )
    op.create_index(
        "idx_conversation_turns_conversation_created",
        "conversation_turns",
        ["conversation_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "context_chains",
        sa.Column("chain_id", sa.String(length=100), nullable=False),
        sa.Column("conversation_id", sa.String(length=100), nullable=False),
        sa.Column("resources", sa.JSON(), nullable=False),
        sa.Column("last_active_at", sa.DateTime(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("chain_id"),
    )
    op.create_index(
        "idx_context_chains_conversation_active",
        "context_chains",
        ["conversation_id", "archived", "last_active_at"],
        unique=False,
    )

    op.create_table(
        "context_chain_nodes",
        sa.Column("node_id", sa.String(length=100), nullable=False),
        sa.Column("chain_id", sa.String(length=100), nullable=False),
        sa.Column("turn_id", sa.String(length=100), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("related_task_ids", sa.JSON(), nullable=False),
        sa.Column("related_resource_refs", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["chain_id"],
            ["context_chains.chain_id"],
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["conversation_turns.turn_id"],
        ),
        sa.PrimaryKeyConstraint("node_id"),
        sa.UniqueConstraint(
            "chain_id",
            "sequence",
            name="uq_context_chain_nodes_chain_sequence",
        ),
        sa.UniqueConstraint(
            "chain_id",
            "turn_id",
            name="uq_context_chain_nodes_chain_turn",
        ),
    )
    op.create_index(
        "idx_context_chain_nodes_turn",
        "context_chain_nodes",
        ["turn_id"],
        unique=False,
    )

    op.create_table(
        "context_route_decisions",
        sa.Column("route_id", sa.String(length=100), nullable=False),
        sa.Column("conversation_id", sa.String(length=100), nullable=False),
        sa.Column("current_turn_id", sa.String(length=100), nullable=False),
        sa.Column("selected_chain_ids", sa.JSON(), nullable=False),
        sa.Column("create_new_chain", sa.Boolean(), nullable=False),
        sa.Column("route_mode", sa.String(length=30), nullable=False),
        sa.Column("reason_summary", sa.Text(), nullable=False),
        sa.Column("new_chain_id", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["current_turn_id"],
            ["conversation_turns.turn_id"],
        ),
        sa.PrimaryKeyConstraint("route_id"),
        sa.UniqueConstraint(
            "current_turn_id",
            name="uq_context_route_decisions_turn",
        ),
    )
    op.create_index(
        "idx_context_route_decisions_conversation_created",
        "context_route_decisions",
        ["conversation_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """按依赖逆序移除 Context 子系统数据表。"""
    op.drop_index(
        "idx_context_route_decisions_conversation_created",
        table_name="context_route_decisions",
    )
    op.drop_table("context_route_decisions")
    op.drop_index(
        "idx_context_chain_nodes_turn",
        table_name="context_chain_nodes",
    )
    op.drop_table("context_chain_nodes")
    op.drop_index(
        "idx_context_chains_conversation_active",
        table_name="context_chains",
    )
    op.drop_table("context_chains")
    op.drop_index(
        "idx_conversation_turns_conversation_created",
        table_name="conversation_turns",
    )
    op.drop_table("conversation_turns")
