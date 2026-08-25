"""登记 documents 表的原始文件名（original_filename）与文件大小（file_size）字段。

由于上述两个字段在引入自动化 Alembic 迁移脚本之前已在生产/开发库通过人工 DDL 添加，
本迁移仅作为版本链条跟踪节点存在，在 upgrade/downgrade 中不执行重复 DDL，避免产生字段冲突或误删数据。

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
    """升级操作：字段已在迁移前通过手工 DDL 完成创建，此处仅记录版本链条，不重复执行 DDL。"""
    pass


def downgrade() -> None:
    """降级操作：不执行 DROP COLUMN，避免在回滚时误删生产环境中的原始文件名与文件大小真实数据。"""
    pass
