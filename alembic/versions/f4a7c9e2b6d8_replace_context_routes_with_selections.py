"""replace context routes with selections

Revision ID: f4a7c9e2b6d8
Revises: d8f2a4c6e9b1
Create Date: 2026-08-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a7c9e2b6d8"
down_revision: Union[str, Sequence[str], None] = "d8f2a4c6e9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("context_route_decisions", "context_selection_records")
    op.drop_index(
        "idx_context_route_decisions_conversation_created",
        table_name="context_selection_records",
    )
    op.drop_constraint(
        "uq_context_route_decisions_turn",
        "context_selection_records",
        type_="unique",
    )
    op.alter_column(
        "context_selection_records",
        "route_id",
        new_column_name="selection_id",
        existing_type=sa.String(length=100),
        existing_nullable=False,
    )
    op.alter_column(
        "context_selection_records",
        "selected_chain_ids",
        new_column_name="relevant_chain_ids",
        existing_type=sa.JSON(),
        existing_nullable=False,
    )
    op.alter_column(
        "context_selection_records",
        "route_mode",
        new_column_name="selection_mode",
        existing_type=sa.String(length=30),
        existing_nullable=False,
    )
    op.execute(
        sa.text(
            "UPDATE conversation_turns "
            "SET status = 'context_ready' WHERE status = 'routed'"
        )
    )
    # 旧路由阶段已为未完成 Turn 建立 placeholder Node。新生命周期只在
    # Complete transaction 创建最终 Node，因此升级时移除这些非事实成员关系。
    op.execute(
        sa.text(
            "DELETE n FROM context_chain_nodes AS n "
            "INNER JOIN context_selection_records AS r "
            "ON r.current_turn_id = n.turn_id "
            "INNER JOIN conversation_turns AS t "
            "ON t.turn_id = r.current_turn_id "
            "WHERE t.status IN ('context_ready', 'processing')"
        )
    )
    # 仅删除旧路由为未完成 Turn 预建、且没有任何正式事实的空 Chain。
    op.execute(
        sa.text(
            "DELETE c FROM context_chains AS c "
            "INNER JOIN context_selection_records AS r "
            "ON r.new_chain_id = c.chain_id "
            "INNER JOIN conversation_turns AS t "
            "ON t.turn_id = r.current_turn_id "
            "LEFT JOIN context_chain_nodes AS n ON n.chain_id = c.chain_id "
            "LEFT JOIN context_chain_resources AS cr "
            "ON cr.chain_id = c.chain_id "
            "LEFT JOIN context_chain_resource_events AS ce "
            "ON ce.chain_id = c.chain_id "
            "WHERE t.status IN ('context_ready', 'processing') "
            "AND n.node_id IS NULL AND cr.id IS NULL "
            "AND ce.event_id IS NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE context_selection_records "
            "SET selection_mode = CASE "
            "WHEN JSON_LENGTH(relevant_chain_ids) = 0 THEN 'no_context' "
            "WHEN JSON_LENGTH(relevant_chain_ids) = 1 THEN 'single_context' "
            "ELSE 'multi_context' END"
        )
    )
    op.drop_column("context_selection_records", "create_new_chain")
    op.drop_column("context_selection_records", "new_chain_id")
    op.create_unique_constraint(
        "uq_context_selection_records_turn",
        "context_selection_records",
        ["current_turn_id"],
    )
    op.create_index(
        "idx_context_selection_records_conversation_created",
        "context_selection_records",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Context Selection/Attribution migration is irreversible; "
        "restore a pre-upgrade database backup before running the previous "
        "application version."
    )
