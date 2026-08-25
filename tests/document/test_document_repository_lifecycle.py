"""DocumentRepository 生命周期状态更新与悲观行锁测试。

核心业务不变量（遵循 AGENTS.md 规范）：
1. 行级排他锁（FOR UPDATE）：
   - `get_by_id_for_update` 在事务中附加悲观行锁，防止并发执行者读取或修改脏状态。
2. 三状态轴与哈希更新：
   - `update_lifecycle_state` 在锁内安全更新 `lifecycle_status`、`storage_status`、`active_content_hash` 及相关时间戳，并保证仅执行 flush 而不越权 commit。
"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.modules.document.domain.enums import (
    DocumentLifecycleStatus,
    DocumentStorageStatus,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
REPOSITORY_PATH = (
    ROOT_DIR
    / "app"
    / "modules"
    / "document"
    / "infrastructure"
    / "persistence"
    / "document_repository.py"
)


class _Field:
    """测试用 SQLAlchemy Column 表达式替身。"""
    def __eq__(self, other):
        return ("eq", other)

    def in_(self, values):
        return ("in", tuple(values))


class _DocumentModel:
    """测试用 Document ORM 字段定义替身。"""
    id = _Field()
    kb_id = _Field()
    active_content_hash = _Field()


def _load_repository_module():
    sqlalchemy_module = types.ModuleType("sqlalchemy")
    sqlalchemy_module.or_ = lambda *criteria: ("or", criteria)
    sqlalchemy_orm_module = types.ModuleType("sqlalchemy.orm")
    sqlalchemy_orm_module.Session = object
    model_module_name = (
        "app.modules.document.infrastructure.persistence.models.document"
    )
    document_module = types.ModuleType(model_module_name)
    document_module.Document = _DocumentModel

    replacements = {
        "sqlalchemy": sqlalchemy_module,
        "sqlalchemy.orm": sqlalchemy_orm_module,
        model_module_name: document_module,
    }
    originals = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        spec = importlib.util.spec_from_file_location(
            "document_repository_under_test",
            REPOSITORY_PATH,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载待测试的 DocumentRepository")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class _Query:
    def __init__(self, result) -> None:
        self.result = result
        self.filters = []
        self.order_by_fields = []
        self.with_for_update_count = 0

    def filter(self, *criteria):
        self.filters.extend(criteria)
        return self

    def with_for_update(self):
        self.with_for_update_count += 1
        return self

    def order_by(self, *fields):
        self.order_by_fields.extend(fields)
        return self

    def first(self):
        return self.result

    def all(self):
        return self.result


class _Session:
    def __init__(self, query: _Query) -> None:
        self.query_result = query
        self.queried_models = []
        self.flush_count = 0

    def query(self, model):
        self.queried_models.append(model)
        return self.query_result

    def flush(self) -> None:
        self.flush_count += 1


class DocumentRepositoryLifecycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository_module = _load_repository_module()

    def test_get_by_id_for_update_applies_row_lock(self) -> None:
        document = SimpleNamespace(id=7)
        query = _Query(document)
        repository = self.repository_module.DocumentRepository(_Session(query))

        result = repository.get_by_id_for_update(7)

        self.assertIs(result, document)
        self.assertEqual(query.filters, [("eq", 7)])
        self.assertEqual(query.with_for_update_count, 1)

    def test_get_by_ids_for_update_sorts_deduplicates_and_locks(self) -> None:
        documents = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        query = _Query(documents)
        repository = self.repository_module.DocumentRepository(_Session(query))

        result = repository.get_by_ids_for_update([2, 1, 2])

        self.assertEqual(result, documents)
        self.assertEqual(query.filters, [("in", (1, 2))])
        self.assertEqual(
            query.order_by_fields,
            [self.repository_module.Document.id],
        )
        self.assertEqual(query.with_for_update_count, 1)

    def test_get_by_ids_for_update_does_not_query_for_empty_ids(self) -> None:
        query = _Query([])
        session = _Session(query)
        repository = self.repository_module.DocumentRepository(session)

        result = repository.get_by_ids_for_update([])

        self.assertEqual(result, [])
        self.assertEqual(session.queried_models, [])

    def test_deactivate_updates_axes_and_only_flushes(self) -> None:
        session = _Session(_Query(None))
        repository = self.repository_module.DocumentRepository(session)
        document = SimpleNamespace(
            status="indexed",
            lifecycle_status="active",
            active_content_hash="hash-a",
            storage_status="active",
            replaced_by=None,
        )

        result = repository.deactivate(
            document,
            DocumentLifecycleStatus.REPLACED.value,
            replaced_by=9,
        )

        self.assertIs(result, document)
        self.assertEqual(document.status, "indexed")
        self.assertEqual(document.lifecycle_status, "replaced")
        self.assertIsNone(document.active_content_hash)
        self.assertEqual(
            document.storage_status,
            DocumentStorageStatus.ARCHIVING.value,
        )
        self.assertEqual(document.replaced_by, 9)
        self.assertEqual(session.flush_count, 1)


if __name__ == "__main__":
    unittest.main()
