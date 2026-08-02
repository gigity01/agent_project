"""ChildChunkRepository 索引领取、行锁和状态批量更新测试。"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_PATH = (
    ROOT_DIR
    / "app"
    / "modules"
    / "document"
    / "infrastructure"
    / "persistence"
    / "child_chunk_repository.py"
)


class _Field:
    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def __ne__(self, other):
        return ("ne", self.name, other)

    def in_(self, values):
        return ("in", self.name, tuple(values))

    def asc(self):
        return ("asc", self.name)


class _ChildChunkModel:
    id = _Field("id")
    doc_id = _Field("doc_id")
    parent_id = _Field("parent_id")
    chunk_index = _Field("chunk_index")
    status = _Field("status")
    vector_status = _Field("vector_status")


class _Func:
    @staticmethod
    def count(field):
        return ("count", field.name)


def _load_repository_module():
    sqlalchemy_module = types.ModuleType("sqlalchemy")
    sqlalchemy_module.func = _Func()
    sqlalchemy_orm_module = types.ModuleType("sqlalchemy.orm")
    sqlalchemy_orm_module.Session = object
    model_module_name = (
        "app.modules.document.infrastructure.persistence.models.child_chunk"
    )
    document_module = types.ModuleType(model_module_name)
    document_module.ChildChunk = _ChildChunkModel
    replacements = {
        "sqlalchemy": sqlalchemy_module,
        "sqlalchemy.orm": sqlalchemy_orm_module,
        model_module_name: document_module,
    }
    originals = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        spec = importlib.util.spec_from_file_location(
            "child_chunk_repository_under_test",
            REPOSITORY_PATH,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载待测试的 ChildChunkRepository")
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
        self.group_by_fields = []
        self.with_for_update_count = 0

    def filter(self, *criteria):
        self.filters.extend(criteria)
        return self

    def order_by(self, *fields):
        self.order_by_fields.extend(fields)
        return self

    def group_by(self, *fields):
        self.group_by_fields.extend(fields)
        return self

    def with_for_update(self):
        self.with_for_update_count += 1
        return self

    def all(self):
        return self.result

    def first(self):
        return self.result[0] if self.result else None

    def count(self):
        return len(self.result)


class _Session:
    def __init__(self, query: _Query) -> None:
        self.query_result = query
        self.queried_models = []
        self.flush_count = 0

    def query(self, *models):
        self.queried_models.extend(models)
        return self.query_result

    def flush(self) -> None:
        self.flush_count += 1


class ChildChunkRepositoryIndexingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository_module = _load_repository_module()

    def test_list_indexable_uses_active_pending_failed_and_stable_order(self) -> None:
        chunks = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        query = _Query(chunks)
        repository = self.repository_module.ChildChunkRepository(_Session(query))

        result = repository.list_indexable_by_doc_id(
            7,
            {"pending", "failed"},
        )

        self.assertEqual(result, chunks)
        self.assertIn(("eq", "doc_id", 7), query.filters)
        self.assertIn(("eq", "status", "active"), query.filters)
        vector_filter = next(item for item in query.filters if item[:2] == ("in", "vector_status"))
        self.assertEqual(set(vector_filter[2]), {"pending", "failed"})
        self.assertEqual(
            query.order_by_fields,
            [("asc", "parent_id"), ("asc", "chunk_index")],
        )

    def test_list_by_ids_sorts_deduplicates_scopes_and_locks(self) -> None:
        chunks = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        query = _Query(chunks)
        repository = self.repository_module.ChildChunkRepository(_Session(query))

        result = repository.list_by_ids_for_update(7, [2, 1, 2])

        self.assertEqual(result, chunks)
        self.assertIn(("eq", "doc_id", 7), query.filters)
        self.assertIn(("in", "id", (1, 2)), query.filters)
        self.assertEqual(
            query.order_by_fields,
            [self.repository_module.ChildChunk.id],
        )
        self.assertEqual(query.with_for_update_count, 1)

    def test_list_by_ids_does_not_query_empty_input(self) -> None:
        query = _Query([])
        session = _Session(query)
        repository = self.repository_module.ChildChunkRepository(session)

        self.assertEqual(repository.list_by_ids_for_update(7, []), [])
        self.assertEqual(session.queried_models, [])

    def test_exists_by_doc_id_and_vector_status_scopes_active_chunks(self) -> None:
        query = _Query([SimpleNamespace(id=1)])
        repository = self.repository_module.ChildChunkRepository(_Session(query))

        self.assertTrue(
            repository.exists_by_doc_id_and_vector_status(7, "indexing")
        )
        self.assertIn(("eq", "doc_id", 7), query.filters)
        self.assertIn(("eq", "status", "active"), query.filters)
        self.assertIn(("eq", "vector_status", "indexing"), query.filters)

    def test_count_active_not_indexed_scopes_document_and_status(self) -> None:
        query = _Query([SimpleNamespace(id=1), SimpleNamespace(id=2)])
        repository = self.repository_module.ChildChunkRepository(_Session(query))

        result = repository.count_active_not_indexed_by_doc_id(7)

        self.assertEqual(result, 2)
        self.assertIn(("eq", "doc_id", 7), query.filters)
        self.assertIn(("eq", "status", "active"), query.filters)
        self.assertIn(("ne", "vector_status", "indexed"), query.filters)

    def test_count_by_vector_status_groups_active_chunks(self) -> None:
        query = _Query([("pending", 2), ("indexed", 3)])
        repository = self.repository_module.ChildChunkRepository(
            _Session(query)
        )

        result = repository.count_by_vector_status_for_document(7)

        self.assertEqual(result, {"pending": 2, "indexed": 3})
        self.assertIn(("eq", "doc_id", 7), query.filters)
        self.assertIn(("eq", "status", "active"), query.filters)
        self.assertEqual(
            query.group_by_fields,
            [self.repository_module.ChildChunk.vector_status],
        )

    def test_batch_indexed_and_failed_updates_only_flush(self) -> None:
        session = _Session(_Query([]))
        repository = self.repository_module.ChildChunkRepository(session)
        indexed_chunks = [
            SimpleNamespace(id=1, vector_status="indexing"),
            SimpleNamespace(id=2, vector_status="indexing"),
        ]

        repository.mark_indexed_many(indexed_chunks)

        self.assertTrue(
            all(chunk.vector_status == "indexed" for chunk in indexed_chunks)
        )
        self.assertEqual(
            [chunk.qdrant_point_id for chunk in indexed_chunks],
            ["1", "2"],
        )
        self.assertTrue(all(chunk.indexed_at is not None for chunk in indexed_chunks))

        failed_chunks = [
            SimpleNamespace(vector_status="indexing"),
            SimpleNamespace(vector_status="indexed"),
        ]
        repository.mark_failed(failed_chunks)

        self.assertEqual(failed_chunks[0].vector_status, "failed")
        self.assertEqual(failed_chunks[1].vector_status, "indexed")
        self.assertEqual(session.flush_count, 2)


if __name__ == "__main__":
    unittest.main()
