"""数据库基础模式基线（Baseline）标记迁移。

本迁移作为 Alembic 迁移链的初始起点（down_revision 为 None），将版本历史锚定到已经存在的初始数据库物理结构。
该迁移不包含实质性的 DDL 变更语句，仅用于建立版本控制链条。

Revision ID: da90f1ff6fb9
Revises: None
Create Date: 2026-05-25 15:16:30.912854
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da90f1ff6fb9'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """基线迁移：不执行任何 DDL 变更，仅标记既有物理 Schema 的初始版本起点。"""
    pass


def downgrade() -> None:
    """基线降级：初始基线无前置版本与可回滚 DDL，执行空操作。"""
    pass
