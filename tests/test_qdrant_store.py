"""QdrantVectorStore 稳定 Point ID 删除接口的轻量测试。"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
STORE_PATH = ROOT_DIR / "app" / "vectorstores" / "qdrant_store.py"


class _PointIdsList:
    def __init__(self, *, points: list[int]) -> None:
        self.points = points


class _VectorParams:
    def __init__(self, **values) -> None:
        self.values = values


class _Distance:
    COSINE = "cosine"


class _Client:
    def __init__(self) -> None:
        self.delete_calls: list[dict] = []

    def delete(self, **values) -> None:
        self.delete_calls.append(values)


def _load_store_module(client: _Client):
    qdrant_module = types.ModuleType("qdrant_client")
    qdrant_models_module = types.ModuleType("qdrant_client.models")
    settings_module = types.ModuleType("app.app_config.settings")
    qdrant_module.QdrantClient = lambda url: client
    qdrant_models_module.Distance = _Distance
    qdrant_models_module.PointIdsList = _PointIdsList
    qdrant_models_module.PointStruct = object
    qdrant_models_module.VectorParams = _VectorParams
    settings_module.QDRANT_URL = "http://qdrant.invalid"
    settings_module.QDRANT_COLLECTION_NAME = "chunks"
    settings_module.EMBEDDING_VECTOR_SIZE = 3
    replacements = {
        "qdrant_client": qdrant_module,
        "qdrant_client.models": qdrant_models_module,
        "app.app_config.settings": settings_module,
    }
    originals = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        spec = importlib.util.spec_from_file_location(
            "qdrant_store_under_test",
            STORE_PATH,
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("无法加载待测试的 QdrantVectorStore")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class QdrantVectorStoreTest(unittest.TestCase):
    def test_delete_points_uses_point_ids_selector_and_waits(self) -> None:
        client = _Client()
        store_module = _load_store_module(client)
        store = store_module.QdrantVectorStore()

        store.delete_points([1, 2])

        self.assertEqual(len(client.delete_calls), 1)
        call = client.delete_calls[0]
        self.assertEqual(call["collection_name"], "chunks")
        self.assertEqual(call["points_selector"].points, [1, 2])
        self.assertTrue(call["wait"])

    def test_delete_points_skips_empty_ids(self) -> None:
        client = _Client()
        store_module = _load_store_module(client)
        store = store_module.QdrantVectorStore()

        store.delete_points([])

        self.assertEqual(client.delete_calls, [])


if __name__ == "__main__":
    unittest.main()
