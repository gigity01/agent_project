"""Context Selection 数据库迁移与 ORM 实体字段对齐测试。

核心业务不变量：
1. 迁移操作语义验证：
   - 验证迁移脚本正确将 `context_route_decisions` 重命名为 `context_selection_records`。
   - 验证列更名（route_id -> selection_id, selected_chain_ids -> relevant_chain_ids, route_mode -> selection_mode）。
   - 验证删除旧架构多余列（create_new_chain, new_chain_id）并清理未完成轮次的非事实占位节点与空链。
   - 验证迁移的单向性（不可逆，downgrade 抛出 RuntimeError）。
2. ORM 模型对齐：
   - 确保 ContextSelectionRecord ORM 实体表名与列定义与迁移后的数据库物理 Schema 完全一致。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest
from unittest import mock

from app.modules.context.infrastructure.persistence.models.context_selection_record import (
    ContextSelectionRecord,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    ROOT_DIR
    / "alembic"
    / "versions"
    / "f4a7c9e2b6d8_replace_context_routes_with_selections.py"
)


def _load_migration():
    """动态加载 Context Selection Alembic 迁移脚本。"""
    spec = importlib.util.spec_from_file_location(
        "context_selection_migration_under_test",
        MIGRATION_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 Context Selection migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ContextSelectionMigrationTest(unittest.TestCase):
    """验证 Context Selection 迁移升级/降级逻辑及 ORM 模型列定义。"""

    def test_upgrade_renames_contract_and_removes_placeholders(self) -> None:
        """验证 upgrade 执行了表重命名、列重命名、索引就地重命名及脏数据清理。"""
        migration = _load_migration()
        operations = mock.Mock()
        migration.op = operations

        migration.upgrade()

        operations.rename_table.assert_called_once_with(
            "context_route_decisions",
            "context_selection_records",
        )
        renamed_columns = {
            call.args[1]: call.kwargs["new_column_name"]
            for call in operations.alter_column.call_args_list
        }
        self.assertEqual(
            renamed_columns,
            {
                "route_id": "selection_id",
                "selected_chain_ids": "relevant_chain_ids",
                "route_mode": "selection_mode",
            },
        )
        self.assertEqual(
            [call.args[1] for call in operations.drop_column.call_args_list],
            ["create_new_chain", "new_chain_id"],
        )
        statements = "\n".join(
            str(call.args[0]) for call in operations.execute.call_args_list
        )
        self.assertIn(
            "RENAME INDEX uq_context_route_decisions_turn "
            "TO uq_context_selection_records_turn",
            statements,
        )
        self.assertIn(
            "RENAME INDEX idx_context_route_decisions_conversation_created "
            "TO idx_context_selection_records_conversation_created",
            statements,
        )
        operations.drop_constraint.assert_not_called()
        operations.drop_index.assert_not_called()
        operations.create_unique_constraint.assert_not_called()
        operations.create_index.assert_not_called()
        self.assertIn("status = 'context_ready'", statements)
        self.assertIn("DELETE n FROM context_chain_nodes", statements)
        self.assertIn("DELETE c FROM context_chains", statements)
        self.assertIn("JSON_LENGTH(relevant_chain_ids)", statements)
        self.assertEqual(migration.down_revision, "d8f2a4c6e9b1")

    def test_downgrade_fails_closed_because_attribution_is_not_recoverable(
        self,
    ) -> None:
        """验证 downgrade 抛出不可逆异常，防止非结构化回退损坏归属事实。"""
        migration = _load_migration()

        with self.assertRaisesRegex(RuntimeError, "irreversible"):
            migration.downgrade()

    def test_orm_exposes_only_selection_fields(self) -> None:
        """验证 ContextSelectionRecord ORM 实体字段集合严格与新架构定义匹配。"""
        columns = ContextSelectionRecord.__table__.c

        self.assertEqual(
            set(columns.keys()),
            {
                "selection_id",
                "conversation_id",
                "current_turn_id",
                "relevant_chain_ids",
                "selection_mode",
                "reason_summary",
                "created_at",
            },
        )
        self.assertEqual(
            ContextSelectionRecord.__tablename__,
            "context_selection_records",
        )


if __name__ == "__main__":
    unittest.main()
