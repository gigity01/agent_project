"""文档三状态轴与有效内容 Hash 迁移的不变量测试。"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.constants.document_status import DocumentStatus


ROOT_DIR = Path(__file__).resolve().parents[1]
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
    """以轻量替身加载 migration，避免测试依赖项目未声明的第三方包。"""
    alembic_module = types.ModuleType("alembic")
    alembic_module.context = SimpleNamespace(is_offline_mode=lambda: False)
    alembic_module.op = SimpleNamespace()

    sqlalchemy_module = types.ModuleType("sqlalchemy")
    sqlalchemy_module.Column = _Column
    sqlalchemy_module.String = _String
    sqlalchemy_module.text = lambda statement: statement

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


class _Result:
    def __init__(self, cursor: sqlite3.Cursor) -> None:
        self.cursor = cursor

    def first(self) -> SimpleNamespace | None:
        row = self.cursor.fetchone()
        if row is None:
            return None
        return SimpleNamespace(**dict(row))


class _Bind:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def execute(self, statement: str) -> _Result:
        return _Result(self.connection.execute(str(statement)))


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

    def get_bind(self) -> _Bind:
        return _Bind(self.connection)

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
        self.migration.context = SimpleNamespace(is_offline_mode=lambda: False)

    def tearDown(self) -> None:
        self.connection.close()

    def _insert(self, kb_id: int, content_hash: str, status: str) -> None:
        self.connection.execute(
            "INSERT INTO documents (kb_id, content_hash, status) VALUES (?, ?, ?)",
            (kb_id, content_hash, status),
        )

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

    def test_upgrade_backfills_three_state_axes_without_releasing_active_hash(self) -> None:
        statuses = [
            "scheduled",
            "active",
            "expired",
            "replaced",
            "deleted",
            "archived",
            "processing",
            "chunking",
            "indexing",
            "failed",
        ]
        for index, status in enumerate(statuses, start=1):
            self._insert(1, f"hash-{index}", status)

        self.migration.upgrade()

        rows = {
            row["status"]: row
            for row in self.connection.execute("SELECT * FROM documents")
        }
        for status in ("scheduled", "active"):
            self.assertEqual(rows[status]["lifecycle_status"], status)
            self.assertEqual(
                rows[status]["active_content_hash"],
                rows[status]["content_hash"],
            )
        for status in ("expired", "replaced", "deleted"):
            self.assertEqual(rows[status]["lifecycle_status"], status)
            self.assertIsNone(rows[status]["active_content_hash"])
        for status in ("processing", "chunking", "indexing", "failed"):
            self.assertEqual(rows[status]["lifecycle_status"], "active")
            self.assertEqual(
                rows[status]["active_content_hash"],
                rows[status]["content_hash"],
            )
        self.assertEqual(rows["archived"]["lifecycle_status"], "active")
        self.assertEqual(rows["archived"]["storage_status"], "archived")
        self.assertEqual(
            rows["archived"]["active_content_hash"],
            rows["archived"]["content_hash"],
        )

    def test_unique_constraint_scopes_non_null_hash_to_knowledge_base(self) -> None:
        self.migration.upgrade()
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

        self.connection.execute(
            """
            INSERT INTO documents
                (kb_id, content_hash, status, active_content_hash)
            VALUES (2, 'hash-a', 'uploaded', 'hash-a')
            """
        )
        self.connection.executemany(
            """
            INSERT INTO documents
                (kb_id, content_hash, status, active_content_hash)
            VALUES (1, ?, 'uploaded', NULL)
            """,
            [("inactive-a",), ("inactive-b",)],
        )

    def test_upgrade_releases_inactive_duplicate_before_conflict_check(self) -> None:
        self._insert(1, "shared-hash", "active")
        self._insert(1, "shared-hash", "expired")

        self.migration.upgrade()

        rows = self.connection.execute(
            """
            SELECT status, active_content_hash
            FROM documents
            ORDER BY id
            """
        ).fetchall()
        self.assertEqual(rows[0]["active_content_hash"], "shared-hash")
        self.assertIsNone(rows[1]["active_content_hash"])
        self.assertTrue(self.operations.unique_constraint_created)

    def test_upgrade_stops_on_active_hash_conflict_without_choosing_a_record(self) -> None:
        self._insert(1, "duplicate-hash", "active")
        self._insert(1, "duplicate-hash", "processing")

        with self.assertRaisesRegex(
            RuntimeError,
            r"kb_id=1, hash=duplicate-hash, count=2",
        ):
            self.migration.upgrade()

        self.assertFalse(self.operations.unique_constraint_created)
        rows = self.connection.execute(
            "SELECT active_content_hash FROM documents ORDER BY id"
        ).fetchall()
        self.assertEqual(
            [row["active_content_hash"] for row in rows],
            ["duplicate-hash", "duplicate-hash"],
        )
        indexes = self.connection.execute(
            "PRAGMA index_list('documents')"
        ).fetchall()
        self.assertEqual(indexes, [])


if __name__ == "__main__":
    unittest.main()
