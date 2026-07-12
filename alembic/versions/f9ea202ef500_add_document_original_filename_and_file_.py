"""add document original filename and file size

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
    # Schema already changed manually:
    # documents.original_filename
    # documents.file_size
    pass


def downgrade() -> None:
    pass
