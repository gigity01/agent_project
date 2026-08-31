"""ChildChunkRepository 向量索引候选筛选、行级排他锁与批量状态更新测试。

核心业务不变量（遵循 AGENTS.md 规范）：
1. 索引候选子集筛选（Claim 阶段）：
   - `list_indexable_by_doc_id` 仅查询 `status=active` 且 `vector_status in (pending, failed)` 的子块，
     已成功索引的子块绝不重复生成向量。
   - 按 `(parent_id ASC, chunk_index ASC)` 稳定排序，保证分块处理顺序确定性。
2. 悲观行锁防并发（Lock 阶段）：
   - `list_by_ids_for_update` 使用 `with_for_update()` 执行 SELECT ... FOR UPDATE，
     按 `id ASC` 排序并去重，避免死锁并防止并发 Worker 重复索引相同 Chunk。
3. 状态与 Point ID 映射：
   - `mark_indexed_many` 将子块 `vector_status` 推进为 `indexed`，并将 `qdrant_point_id` 与 `child_chunks.id` 一一对应绑定。
"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT_DIR = Path(__file__).resolve().parents[2]
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
    """测试用 SQLAlchemy Column 表达式替身，支持条件过滤与排序操作。"""

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
    """测试用 ChildChunk ORM 实体字段定义替身。"""

    id = _Field("id")
    doc_id = _Field("doc_id")
    parent_id = _Field("parent_id")
    chunk_index = _Field("chunk_index")
    status = _Field("status")
    vector_status = _Field("vector_status")


class _Func:
    """测试用 SQLAlchemy func 聚合函数替身。"""

    @staticmethod
    def count(field):
        return ("count", field.name)


def _load_repository_module():
    """动态加载 ChildChunkRepository 模块并注入测试用轻量 SQLAlchemy 替身。"""
    sqlalchemy_module = types.ModuleType("sqlalchemy")
    sqlalchemy_module.String = object
    sqlalchemy_module.cast = lambda value, _type: value
    sqlalchemy_module.func = _Func()
    sqlalchemy_module.or_ = lambda *criteria: ("or", criteria)
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
    """测试用 SQLAlchemy Query 替身，捕获 filter, order_by, group_by 与 with_for_update 调用。"""

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
    """测试用 SQLAlchemy Session 替身，记录 query 模型与 flush 次数。"""

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
    """验证 ChildChunkRepository 中支持向量索引流水线的查询与批量更新方法。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repository_module = _load_repository_module()

    def test_list_indexable_uses_active_pending_failed_and_stable_order(self) -> None:
        """验证 list_indexable_by_doc_id 严格限定 active 且待索引/失败状态，并按 parent_id, chunk_index 稳定排序。"""
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
        """验证 list_by_ids_for_update 对传入 ID 列表去重、按 id 排序并附加 FOR UPDATE 排他行锁。"""
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
        """验证传入空 ID 列表时直接返回空列表，不产生任何数据库查询。"""
        query = _Query([])
        session = _Session(query)
        repository = self.repository_module.ChildChunkRepository(session)

        self.assertEqual(repository.list_by_ids_for_update(7, []), [])
        self.assertEqual(session.queried_models, [])

    def test_exists_by_doc_id_and_vector_status_scopes_active_chunks(self) -> None:
        """验证 exists_by_doc_id_and_vector_status 仅在 active 激活态分块中检查指定向量状态。"""
        query = _Query([SimpleNamespace(id=1)])
        repository = self.repository_module.ChildChunkRepository(_Session(query))

        self.assertTrue(
            repository.exists_by_doc_id_and_vector_status(7, "indexing")
        )
        self.assertIn(("eq", "doc_id", 7), query.filters)
        self.assertIn(("eq", "status", "active"), query.filters)
        self.assertIn(("eq", "vector_status", "indexing"), query.filters)

    def test_count_active_not_indexed_scopes_document_and_status(self) -> None:
        """验证 count_active_not_indexed_by_doc_id 正确统计尚未完成索引的活跃子块数量。"""
        query = _Query([SimpleNamespace(id=1), SimpleNamespace(id=2)])
        repository = self.repository_module.ChildChunkRepository(_Session(query))

        result = repository.count_active_not_indexed_by_doc_id(7)

        self.assertEqual(result, 2)
        self.assertIn(("eq", "doc_id", 7), query.filters)
        self.assertIn(("eq", "status", "active"), query.filters)
        self.assertIn(("ne", "vector_status", "indexed"), query.filters)

    def test_count_by_vector_status_groups_active_chunks(self) -> None:
        """验证 count_by_vector_status_for_document 按 vector_status 分组聚合各状态的活跃分块计数。"""
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
        """验证 mark_indexed_many 与 mark_failed 正确批量更新状态，且仅执行 session.flush() 不越权 commit。"""
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
