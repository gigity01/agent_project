"""TaskExecution 补偿超限锁定字段 Alembic 迁移（d8f2a4c6e9b1）与 ORM 模型对齐测试。

核心业务不变量（遵循 AGENTS.md 规范）：
1. 补偿超限持久化锁定字段：
   - 增加 `compensation_attempt_count`、`compensation_last_error`、`compensation_last_attempt_at`、`compensation_locked_at`、`compensation_lock_reason` 列。
   - 当多次补偿调用持续失败达到上限后，TaskExecution 被正式标记为锁定，防止死循环补偿。
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
    / "d8f2a4c6e9b1_lock_exhausted_task_compensation.py"
)


def _load_migration():
    """动态加载 TaskExecution 补偿锁定迁移脚本。"""
    spec = importlib.util.spec_from_file_location(
        "task_execution_compensation_lock_migration_under_test",
        MIGRATION_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 TaskExecution compensation lock migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TaskExecutionCompensationLockMigrationTest(unittest.TestCase):
    """验证 TaskExecution 补偿锁定列的添加与 ORM 模型对齐。"""
    def test_upgrade_adds_compensation_lock_columns(self) -> None:
        migration = _load_migration()
        operations = mock.Mock()
        migration.op = operations

        migration.upgrade()

        columns = [
            call.args[1]
            for call in operations.add_column.call_args_list
        ]
        self.assertEqual(
            [column.name for column in columns],
            [
                "compensation_attempt_count",
                "compensation_last_error",
                "compensation_last_attempt_at",
                "compensation_locked_at",
                "compensation_lock_reason",
            ],
        )
        self.assertFalse(columns[0].nullable)
        self.assertIsNotNone(columns[0].server_default)
        self.assertEqual(migration.down_revision, "c2d4e6f8a0b1")

    def test_orm_columns_match_migration(self) -> None:
        columns = TaskExecution.__table__.c

        self.assertFalse(columns.compensation_attempt_count.nullable)
        self.assertEqual(columns.compensation_attempt_count.default.arg, 0)
        self.assertTrue(columns.compensation_last_error.nullable)
        self.assertTrue(columns.compensation_last_attempt_at.nullable)
        self.assertTrue(columns.compensation_locked_at.nullable)
        self.assertTrue(columns.compensation_lock_reason.nullable)


if __name__ == "__main__":
    unittest.main()
