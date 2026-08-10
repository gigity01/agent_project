"""add document operation ownership

Revision ID: b1c3d5e7f9a2
Revises: a8d2e4f6b1c3
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c3d5e7f9a2"
down_revision: Union[str, Sequence[str], None] = "a8d2e4f6b1c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "active_operation_id",
            sa.String(length=100),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_documents_active_operation_id",
        "documents",
        ["active_operation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_documents_active_operation_id",
        table_name="documents",
    )
    op.drop_column("documents", "active_operation_id")
