"""Clarification source Turn 唯一约束迁移测试。"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest import mock

import sqlalchemy as sa

from app.modules.clarification.infrastructure.persistence.models import (
    ClarificationRequest,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    ROOT_DIR
    / "alembic"
    / "versions"
    / "9a7c5e3d1b2f_add_clarification_source_turn_unique.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "clarification_source_turn_migration_under_test",
        MIGRATION_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 Clarification source Turn migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ClarificationSourceTurnMigrationTest(unittest.TestCase):
    def test_upgrade_and_downgrade_manage_unique_constraint(self) -> None:
        migration = _load_migration()
        operations = mock.Mock()
        operations.get_bind.return_value.execute.return_value.first.return_value = (
            None
        )
        migration.op = operations

        migration.upgrade()
        migration.downgrade()

        operations.create_unique_constraint.assert_called_once_with(
            "uq_clarification_requests_source_turn",
            "clarification_requests",
            ["source_turn_id"],
        )
        operations.drop_constraint.assert_called_once_with(
            "uq_clarification_requests_source_turn",
            "clarification_requests",
            type_="unique",
        )
        self.assertEqual(migration.down_revision, "4ce8fd45dde4")

    def test_upgrade_fails_closed_when_existing_rows_are_duplicated(
        self,
    ) -> None:
        migration = _load_migration()
        engine = sa.create_engine("sqlite://")
        self.addCleanup(engine.dispose)
        metadata = sa.MetaData()
        table = sa.Table(
            "clarification_requests",
            metadata,
            sa.Column("clarification_id", sa.String(100), primary_key=True),
            sa.Column("source_turn_id", sa.String(100), nullable=False),
        )
        metadata.create_all(engine)

        with engine.begin() as connection:
            connection.execute(
                table.insert(),
                [
                    {
                        "clarification_id": "clarification-1",
                        "source_turn_id": "turn-1",
                    },
                    {
                        "clarification_id": "clarification-2",
                        "source_turn_id": "turn-1",
                    },
                ],
            )
            operations = mock.Mock()
            operations.get_bind.return_value = connection
            migration.op = operations

            with self.assertRaisesRegex(
                RuntimeError,
                "存在重复 source_turn_id",
            ):
                migration.upgrade()

            operations.create_unique_constraint.assert_not_called()

    def test_orm_declares_source_turn_unique_constraint(self) -> None:
        self.assertIn(
            "uq_clarification_requests_source_turn",
            {
                constraint.name
                for constraint in ClarificationRequest.__table__.constraints
            },
        )


if __name__ == "__main__":
    unittest.main()
