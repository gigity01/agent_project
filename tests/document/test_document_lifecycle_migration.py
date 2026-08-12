"""文档状态轴和有效内容 Hash migration 的结构测试。"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.modules.document.domain.enums import DocumentStatus


ROOT_DIR = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    ROOT_DIR
    / "alembic"
    / "versions"
    / "e7b3c2d4a9f1_add_document_content_uniqueness.py"
)


class _String:
    def __init__(self, length: int) -> None:
        self.length = length


class _Column:
    def __init__(
        self,
        name: str,
        column_type: _String,
        *,
        nullable: bool,
        server_default: str | None = None,
    ) -> None:
        self.name = name
        self.type = column_type
        self.nullable = nullable
        self.server_default = server_default


def _load_migration_module():
    """使用轻量替身加载 migration，避免测试依赖未声明的第三方包。"""
    alembic_module = types.ModuleType("alembic")
    alembic_module.op = SimpleNamespace()

    sqlalchemy_module = types.ModuleType("sqlalchemy")
    sqlalchemy_module.Column = _Column
    sqlalchemy_module.String = _String

    original_alembic = sys.modules.get("alembic")
    original_sqlalchemy = sys.modules.get("sqlalchemy")
    sys.modules["alembic"] = alembic_module
    sys.modules["sqlalchemy"] = sqlalchemy_module
    try:
        spec = importlib.util.spec_from_file_location(
            "document_lifecycle_migration_under_test",
            MIGRATION_PATH,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载待测试的 Alembic migration")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if original_alembic is None:
            sys.modules.pop("alembic", None)
        else:
            sys.modules["alembic"] = original_alembic
        if original_sqlalchemy is None:
            sys.modules.pop("sqlalchemy", None)
        else:
            sys.modules["sqlalchemy"] = original_sqlalchemy


class _Operations:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.unique_constraint_created = False

    def add_column(self, table_name: str, column: _Column) -> None:
        sql = f"ALTER TABLE {table_name} ADD COLUMN {column.name} TEXT"
        if not column.nullable:
            sql += f" NOT NULL DEFAULT '{column.server_default}'"
        self.connection.execute(sql)

    def execute(self, statement: str) -> None:
        self.connection.execute(statement)

    def create_unique_constraint(
        self,
        constraint_name: str,
        table_name: str,
        columns: list[str],
    ) -> None:
        self.connection.execute(
            f"CREATE UNIQUE INDEX {constraint_name} "
            f"ON {table_name} ({', '.join(columns)})"
        )
        self.unique_constraint_created = True


class DocumentLifecycleMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY,
                kb_id INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        self.migration = _load_migration_module()
        self.operations = _Operations(self.connection)
        self.migration.op = self.operations

    def tearDown(self) -> None:
        self.connection.close()

    def test_document_status_only_contains_processing_stages(self) -> None:
        self.assertEqual(
            [status.value for status in DocumentStatus],
            [
                "uploaded",
                "processing",
                "processed",
                "chunking",
                "chunked",
                "indexing",
                "indexed",
                "failed",
            ],
        )

    def test_upgrade_adds_state_axes_and_backfills_active_hash(self) -> None:
        self.connection.executemany(
            """
            INSERT INTO documents (kb_id, content_hash, status)
            VALUES (?, ?, 'uploaded')
            """,
            [(1, "hash-a"), (2, "hash-a")],
        )

        self.migration.upgrade()

        rows = self.connection.execute(
            "SELECT * FROM documents ORDER BY id"
        ).fetchall()
        self.assertEqual(
            [row["active_content_hash"] for row in rows],
            ["hash-a", "hash-a"],
        )
        self.assertEqual(
            [row["lifecycle_status"] for row in rows],
            ["active", "active"],
        )
        self.assertEqual(
            [row["storage_status"] for row in rows],
            ["active", "active"],
        )
        self.assertTrue(self.operations.unique_constraint_created)

    def test_unique_constraint_allows_multiple_null_inactive_hashes(self) -> None:
        self.migration.upgrade()
        self.connection.executemany(
            """
            INSERT INTO documents
                (kb_id, content_hash, status, active_content_hash)
            VALUES (1, ?, 'uploaded', NULL)
            """,
            [("inactive-a",), ("inactive-b",)],
        )
        self.connection.execute(
            """
            INSERT INTO documents
                (kb_id, content_hash, status, active_content_hash)
            VALUES (1, 'hash-a', 'uploaded', 'hash-a')
            """
        )

        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                """
                INSERT INTO documents
                    (kb_id, content_hash, status, active_content_hash)
                VALUES (1, 'hash-a', 'uploaded', 'hash-a')
                """
            )


if __name__ == "__main__":
    unittest.main()
