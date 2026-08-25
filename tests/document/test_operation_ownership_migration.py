"""Document active_operation_id 操作所有权 Alembic 迁移（b1c3d5e7f9a2）与 ORM 模型对齐测试。

核心业务不变量（遵循 AGENTS.md 规范）：
1. 迁移 DDL 结构：
   - 验证迁移脚本为 documents 表新增 `active_operation_id VARCHAR(100) NULL` 列及普通索引 `ix_documents_active_operation_id`。
2. ORM 模型对齐：
   - 验证 Document ORM 实体字段定义与迁移结构严格匹配。
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock

from app.modules.document.infrastructure.persistence.models.document import (
    Document,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    ROOT_DIR
    / "alembic"
    / "versions"
    / "b1c3d5e7f9a2_add_document_operation_ownership.py"
)


def _load_migration():
    """动态加载 Operation Ownership Alembic 迁移脚本。"""
    spec = importlib.util.spec_from_file_location(
        "operation_ownership_migration_under_test",
        MIGRATION_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 operation ownership migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OperationOwnershipMigrationTest(unittest.TestCase):
    """验证 active_operation_id 迁移脚本升级与 ORM 映射。"""
    def test_upgrade_adds_nullable_indexed_operation_owner(self) -> None:
        migration = _load_migration()
        operations = mock.Mock()
        migration.op = operations

        migration.upgrade()

        table_name, column = operations.add_column.call_args.args
        self.assertEqual(table_name, "documents")
        self.assertEqual(column.name, "active_operation_id")
        self.assertEqual(column.type.length, 100)
        self.assertTrue(column.nullable)
        operations.create_index.assert_called_once_with(
            "ix_documents_active_operation_id",
            "documents",
            ["active_operation_id"],
            unique=False,
        )
        self.assertEqual(migration.down_revision, "a8d2e4f6b1c3")

    def test_orm_column_matches_migration(self) -> None:
        column = Document.__table__.c.active_operation_id

        self.assertEqual(column.type.length, 100)
        self.assertTrue(column.nullable)
        self.assertTrue(column.index)


if __name__ == "__main__":
    unittest.main()
