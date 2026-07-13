"""登记已手工添加的原始文件名和文件大小字段。

Revision ID: f9ea202ef500
Revises: da90f1ff6fb9
Create Date: 2026-06-03 16:58:10.656437

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9ea202ef500'
down_revision: Union[str, Sequence[str], None] = 'da90f1ff6fb9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 字段已在此迁移生成前由人工变更，故只记录历史而不重复执行 DDL。
    pass


def downgrade() -> None:
    """不回滚已手工维护的字段，避免迁移脚本误删生产数据。"""
    pass
