"""限制一个 Conversation Turn 只创建一个澄清请求。

Revision ID: 9a7c5e3d1b2f
Revises: 4ce8fd45dde4
Create Date: 2026-08-22 14:15:52
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "9a7c5e3d1b2f"
down_revision: Union[str, Sequence[str], None] = "4ce8fd45dde4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _assert_source_turn_ids_are_unique() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            """
            SELECT source_turn_id
            FROM clarification_requests
            GROUP BY source_turn_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "无法创建 uq_clarification_requests_source_turn："
            "clarification_requests 存在重复 source_turn_id，"
            "请先审查并清理重复澄清记录后重试迁移"
        )


def upgrade() -> None:
    _assert_source_turn_ids_are_unique()
    op.create_unique_constraint(
        "uq_clarification_requests_source_turn",
        "clarification_requests",
        ["source_turn_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_clarification_requests_source_turn",
        "clarification_requests",
        type_="unique",
    )
