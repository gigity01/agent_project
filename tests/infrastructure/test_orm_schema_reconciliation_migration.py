"""以 ORM 模型为基准的数据库结构对账 Alembic 迁移（4ce8fd45dde4）结构与安全顺序测试。

核心业务不变量（遵循 AGENTS.md 规范）：
1. 外键支撑索引先行保护（FK Index Preservation）：
   - 在删除旧冗余复合索引（`idx_chunk_kb_status`）之前，必须先创建单列外键支持索引（`idx_child_chunks_kb_id`），防止 MySQL 抛出外键缺失索引约束错误（errno: 150）。
2. 列与表清理安全顺序：
   - 增加 ConversationTurn ORM 模型中的 `clarification_input` 列。
   - 重命名遗留的索引名称与 ORM 命名约定对齐。
   - 最后安全 drop 未在 ORM 声明的遗留旧表（`domains`）。
3. 破坏性数据变更单向性：
   - 降级操作抛出 RuntimeError 拒绝非受控回退。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest import mock

from sqlalchemy import Text

from app.modules.context.infrastructure.persistence.models.conversation_turn import (
    ConversationTurn,
)
from app.modules.document.infrastructure.persistence.models.child_chunk import (
    ChildChunk,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    ROOT_DIR
    / "alembic"
    / "versions"
    / "4ce8fd45dde4_以_orm_为准同步数据库结构.py"
)


def _load_migration():
    """动态加载 ORM Schema 对账 Alembic 迁移脚本。"""
    spec = importlib.util.spec_from_file_location(
        "orm_schema_reconciliation_migration_under_test",
        MIGRATION_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 ORM Schema 对账 migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OrmSchemaReconciliationMigrationTest(unittest.TestCase):
    """验证 ORM 对账迁移的索引保留顺序、新列增加与不可逆保护。"""
    def test_upgrade_preserves_fk_index_before_removing_legacy_indexes(self) -> None:
        migration = _load_migration()
        operations = mock.Mock()
        migration.op = operations

        migration.upgrade()

        operations.create_index.assert_called_once_with(
            "idx_child_chunks_kb_id",
            "child_chunks",
            ["kb_id"],
            unique=False,
        )
        operation_names = [call[0] for call in operations.mock_calls]
        self.assertLess(
            operation_names.index("create_index"),
            operation_names.index("execute"),
        )

        statements = "\n".join(
            str(call.args[0]) for call in operations.execute.call_args_list
        )
        self.assertIn("DROP INDEX idx_chunk_kb_status", statements)
        self.assertIn(
            "RENAME INDEX idx_document_artifacts_document_id "
            "TO ix_document_artifacts_document_id",
            statements,
        )
        operations.drop_index.assert_not_called()

    def test_upgrade_adds_orm_column_and_drops_db_only_table_last(self) -> None:
        migration = _load_migration()
        operations = mock.Mock()
        migration.op = operations

        migration.upgrade()

        operations.add_column.assert_called_once()
        table_name, column = operations.add_column.call_args.args
        self.assertEqual(table_name, "conversation_turns")
        self.assertEqual(column.name, "clarification_input")
        self.assertIsInstance(column.type, Text)
        self.assertTrue(column.nullable)
        operations.drop_table.assert_called_once_with("domains")
        self.assertEqual(operations.mock_calls[-1], mock.call.drop_table("domains"))
        self.assertEqual(migration.down_revision, "f4a7c9e2b6d8")

    def test_downgrade_fails_closed_after_data_destructive_reconciliation(
        self,
    ) -> None:
        migration = _load_migration()

        with self.assertRaisesRegex(RuntimeError, "irreversible"):
            migration.downgrade()

    def test_orm_declares_new_column_and_fk_supporting_index(self) -> None:
        clarification_input = ConversationTurn.__table__.c.clarification_input
        self.assertIsInstance(clarification_input.type, Text)
        self.assertTrue(clarification_input.nullable)
        self.assertIn(
            "idx_child_chunks_kb_id",
            {index.name for index in ChildChunk.__table__.indexes},
        )


if __name__ == "__main__":
    unittest.main()
