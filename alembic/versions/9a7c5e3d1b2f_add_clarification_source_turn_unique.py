"""为 clarification_requests 表添加 source_turn_id 唯一性约束（uq_clarification_requests_source_turn）。

业务背景与设计规范：
1. 澄清模型不变量：
   - 保证同一个 ConversationTurn（source_turn_id）在数据库中至多只能存在一个关联的 ClarificationRequest 记录，
     杜绝因并发 Planner 冲突或重复澄清调用产生多个游离未决请求。
2. 迁移安全性检查：
   - 在执行 DDL 添加唯一约束前，先执行 `_assert_source_turn_ids_are_unique()` 检查，如果发现历史脏数据则主动报错阻断，避免破坏已有数据库。

Revision ID: 9a7c5e3d1b2f
Revises: 4ce8fd45dde4
Create Date: 2026-08-22 14:15:52
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9a7c5e3d1b2f"
down_revision: Union[str, Sequence[str], None] = "4ce8fd45dde4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _assert_source_turn_ids_are_unique() -> None:
    """检查 clarification_requests 中是否存在重复的 source_turn_id，若存在则抛出异常阻断升级。"""
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
