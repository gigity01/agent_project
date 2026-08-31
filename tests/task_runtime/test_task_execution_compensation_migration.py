"""TaskExecution blocked 终态字段 Alembic 迁移（c2d4e6f8a0b1）与 ORM 模型对齐测试。

核心业务不变量（遵循 AGENTS.md 规范）：
1. 迁移 DDL 结构：
   - 为 task_executions 表新增 `blocked BOOLEAN NOT NULL DEFAULT 0` 列。
   - 当任务命令被业务策略直接拒绝（rejected）时标记 blocked，指示无需重试且需要 Replan。
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock

from app.modules.task_runtime.infrastructure.persistence.models import (
    TaskExecution,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    ROOT_DIR
    / "alembic"
    / "versions"
    / "c2d4e6f8a0b1_persist_task_execution_blocked.py"
)


def _load_migration():
    """动态加载 TaskExecution blocked 字段迁移脚本。"""
    spec = importlib.util.spec_from_file_location(
        "task_execution_compensation_migration_under_test",
        MIGRATION_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 TaskExecution compensation migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TaskExecutionCompensationMigrationTest(unittest.TestCase):
    """验证 TaskExecution blocked 字段迁移升级与 ORM 模型对齐。"""
    def test_upgrade_adds_non_nullable_blocked_disposition(self) -> None:
        migration = _load_migration()
        operations = mock.Mock()
        migration.op = operations

        migration.upgrade()

        table_name, column = operations.add_column.call_args.args
        self.assertEqual(table_name, "task_executions")
        self.assertEqual(column.name, "blocked")
        self.assertFalse(column.nullable)
        self.assertIsNotNone(column.server_default)
        self.assertEqual(migration.down_revision, "b1c3d5e7f9a2")

    def test_orm_column_matches_migration(self) -> None:
        column = TaskExecution.__table__.c.blocked

        self.assertFalse(column.nullable)
        self.assertFalse(column.default.arg)


if __name__ == "__main__":
    unittest.main()
