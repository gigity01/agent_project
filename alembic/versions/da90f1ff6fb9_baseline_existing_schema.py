"""将迁移历史锚定到已手工存在的基础 schema。

Revision ID: da90f1ff6fb9
Revises:
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
    """基线迁移不修改数据库结构，只标记既有 schema 的起点。"""
    pass


def downgrade() -> None:
    """基线没有可回滚的 DDL，保留空操作。"""
    pass
