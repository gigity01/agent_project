"""增加 Context Chain 资源事实表和资源版本。

Revision ID: d4f8a1c7e2b9
Revises: b6d9a2e4c8f1
Create Date: 2026-07-26 00:00:00.000000

"""
import json
import re
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4f8a1c7e2b9"
down_revision: Union[str, Sequence[str], None] = "b6d9a2e4c8f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _legacy_resource_pairs(resources: object) -> list[tuple[str, str]]:
    """将旧 ContextResources JSON 转换为正式资源类型和 ID。"""
    if isinstance(resources, str):
        resources = json.loads(resources)
    if not isinstance(resources, dict):
        return []

    field_types = {
        "document_ids": "document",
        "document_codes": "document_code",
        "knowledge_base_ids": "knowledge_base",
        "plan_ids": "plan",
        "task_ids": "task",
        "result_refs": "result",
    }
    pairs: list[tuple[str, str]] = []
    for field, resource_type in field_types.items():
        values = resources.get(field, [])
        if isinstance(values, list):
            pairs.extend((resource_type, str(value)) for value in values)

    other = resources.get("other", {})
    if isinstance(other, dict):
        for raw_type, values in other.items():
            resource_type = str(raw_type)
            if (
                re.fullmatch(r"[a-z][a-z0-9_]*", resource_type) is None
                or len(resource_type) > 100
            ):
                resource_type = "other"
                values = [
                    f"{raw_type}:{value}"
                    for value in values
                ] if isinstance(values, list) else []
            if isinstance(values, list):
                pairs.extend(
                    (resource_type, str(value))
                    for value in values
                )

    return list(dict.fromkeys(pairs))


def _backfill_legacy_resources() -> None:
    """使用每条链的最新 Turn 合成旧资源的初始正式事实。"""
    connection = op.get_bind()
    context_chains = sa.table(
        "context_chains",
        sa.column("chain_id", sa.String()),
        sa.column("resources", sa.JSON()),
        sa.column("resource_version", sa.Integer()),
        sa.column("last_active_at", sa.DateTime()),
    )
    context_chain_nodes = sa.table(
        "context_chain_nodes",
        sa.column("chain_id", sa.String()),
        sa.column("turn_id", sa.String()),
        sa.column("sequence", sa.Integer()),
    )
    resource_states = sa.table(
        "context_chain_resources",
        sa.column("chain_id", sa.String()),
        sa.column("resource_key", sa.String()),
        sa.column("resource_type", sa.String()),
        sa.column("resource_id", sa.String()),
        sa.column("relation", sa.String()),
        sa.column("summary", sa.Text()),
        sa.column("first_seen_turn_id", sa.String()),
        sa.column("last_seen_turn_id", sa.String()),
        sa.column("first_seen_at", sa.DateTime()),
        sa.column("last_seen_at", sa.DateTime()),
        sa.column("use_count", sa.Integer()),
        sa.column("active", sa.Boolean()),
        sa.column("removed_at", sa.DateTime()),
    )
    resource_events = sa.table(
        "context_chain_resource_events",
        sa.column("event_id", sa.String()),
        sa.column("chain_id", sa.String()),
        sa.column("turn_id", sa.String()),
        sa.column("resource_key", sa.String()),
        sa.column("resource_type", sa.String()),
        sa.column("resource_id", sa.String()),
        sa.column("action", sa.String()),
        sa.column("relation", sa.String()),
        sa.column("summary", sa.Text()),
        sa.column("created_at", sa.DateTime()),
    )

    chain_rows = connection.execute(
        sa.select(
            context_chains.c.chain_id,
            context_chains.c.resources,
            context_chains.c.last_active_at,
        )
    ).mappings().all()
    for chain_row in chain_rows:
        pairs = _legacy_resource_pairs(chain_row["resources"])
        if not pairs:
            continue

        turn_id = connection.execute(
            sa.select(context_chain_nodes.c.turn_id)
            .where(
                context_chain_nodes.c.chain_id == chain_row["chain_id"]
            )
            .order_by(context_chain_nodes.c.sequence.desc())
            .limit(1)
        ).scalar_one_or_none()
        if turn_id is None:
            continue

        inserted = 0
        for resource_type, resource_id in pairs:
            resource_key = f"{resource_type}:{resource_id}"
            if len(resource_id) > 400 or len(resource_key) > 512:
                continue
            values = {
                "chain_id": chain_row["chain_id"],
                "resource_key": resource_key,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "relation": None,
                "summary": None,
                "first_seen_turn_id": turn_id,
                "last_seen_turn_id": turn_id,
                "first_seen_at": chain_row["last_active_at"],
                "last_seen_at": chain_row["last_active_at"],
                "use_count": 1,
                "active": True,
                "removed_at": None,
            }
            connection.execute(resource_states.insert().values(**values))
            connection.execute(
                resource_events.insert().values(
                    event_id=f"resource_event_{uuid4().hex}",
                    turn_id=turn_id,
                    action="seen",
                    created_at=chain_row["last_active_at"],
                    **{
                        key: value
                        for key, value in values.items()
                        if key
                        in {
                            "chain_id",
                            "resource_key",
                            "resource_type",
                            "resource_id",
                            "relation",
                            "summary",
                        }
                    },
                )
            )
            inserted += 1

        if inserted:
            connection.execute(
                context_chains.update()
                .where(
                    context_chains.c.chain_id == chain_row["chain_id"]
                )
                .values(resource_version=1)
            )


def upgrade() -> None:
    """创建资源当前状态和追加式历史事件表。"""
    op.add_column(
        "context_chains",
        sa.Column(
            "resource_version",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )

    op.create_table(
        "context_chain_resources",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("chain_id", sa.String(length=100), nullable=False),
        sa.Column("resource_key", sa.String(length=512), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=400), nullable=False),
        sa.Column("relation", sa.String(length=100), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("first_seen_turn_id", sa.String(length=100), nullable=False),
        sa.Column("last_seen_turn_id", sa.String(length=100), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column(
            "use_count",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column("removed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["chain_id"],
            ["context_chains.chain_id"],
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_turn_id"],
            ["conversation_turns.turn_id"],
        ),
        sa.ForeignKeyConstraint(
            ["last_seen_turn_id"],
            ["conversation_turns.turn_id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chain_id",
            "resource_key",
            name="uq_context_chain_resources_chain_resource",
        ),
    )
    op.create_index(
        "idx_context_chain_resources_chain_active_seen",
        "context_chain_resources",
        ["chain_id", "active", "last_seen_at"],
        unique=False,
    )

    op.create_table(
        "context_chain_resource_events",
        sa.Column("event_id", sa.String(length=100), nullable=False),
        sa.Column("chain_id", sa.String(length=100), nullable=False),
        sa.Column("turn_id", sa.String(length=100), nullable=False),
        sa.Column("resource_key", sa.String(length=512), nullable=False),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", sa.String(length=400), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("relation", sa.String(length=100), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "idx_context_resource_events_chain_resource_created",
        "context_chain_resource_events",
        ["chain_id", "resource_key", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_context_resource_events_turn",
        "context_chain_resource_events",
        ["turn_id"],
        unique=False,
    )
    _backfill_legacy_resources()


def downgrade() -> None:
    """移除资源事实表并恢复旧 Context Chain 结构。"""
    op.drop_index(
        "idx_context_resource_events_turn",
        table_name="context_chain_resource_events",
    )
    op.drop_index(
        "idx_context_resource_events_chain_resource_created",
        table_name="context_chain_resource_events",
    )
    op.drop_table("context_chain_resource_events")
    op.drop_index(
        "idx_context_chain_resources_chain_active_seen",
        table_name="context_chain_resources",
    )
    op.drop_table("context_chain_resources")
    op.drop_column("context_chains", "resource_version")
