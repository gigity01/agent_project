"""Context Redis 刷新式 FIFO 队列和客户端工厂的离线测试。"""

from __future__ import annotations

from datetime import datetime, timedelta
import importlib.util
from pathlib import Path
import unittest

from app.modules.context.infrastructure.cache.redis_resource_queue import (
    REFRESH_QUEUE_LUA,
    REPLACE_QUEUE_LUA,
    ContextResourceQueueRepository,
)
from app.infrastructure.redis.client import (
    close_redis_client,
    create_redis_client,
)
from app.modules.context.domain.models import ContextResourceRef


ROOT_DIR = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    ROOT_DIR
    / "alembic"
    / "versions"
    / "d4f8a1c7e2b9_add_context_resource_history.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "context_resource_migration_under_test",
        MIGRATION_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 Context Resource migration")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RedisClient:
    def __init__(self) -> None:
        self.strings = {}
        self.lists = {}
        self.hashes = {}
        self.eval_calls = []

    async def get(self, key):
        return self.strings.get(key)

    async def lrange(self, key, start, end):
        values = list(self.lists.get(key, []))
        return values if end == -1 else values[start : end + 1]

    async def hmget(self, key, fields):
        values = self.hashes.get(key, {})
        return [values.get(field) for field in fields]

    async def delete(self, *keys):
        for key in keys:
            self.strings.pop(key, None)
            self.lists.pop(key, None)
            self.hashes.pop(key, None)

    async def eval(self, script, numkeys, *keys_and_arguments):
        keys = list(keys_and_arguments[:numkeys])
        arguments = list(keys_and_arguments[numkeys:])
        self.eval_calls.append((script, keys, arguments))
        if script == REFRESH_QUEUE_LUA:
            return self._refresh(keys, arguments)
        elif script == REPLACE_QUEUE_LUA:
            return self._replace(keys, arguments)
        else:
            raise AssertionError("Unexpected Lua script")

    def _refresh(self, keys, arguments) -> None:
        queue_key, data_key, version_key = keys
        capacity = int(arguments[0])
        version = str(arguments[1])
        expected_previous_version = str(arguments[2])
        current_version = self.strings.get(version_key)
        if current_version is not None:
            if str(current_version) != expected_previous_version:
                return -1
        elif expected_previous_version != "0":
            return -1

        refresh_count = int(arguments[3])
        index = 4
        queue = list(self.lists.get(queue_key, []))
        data = dict(self.hashes.get(data_key, {}))

        for _ in range(refresh_count):
            resource_key = arguments[index]
            resource_json = arguments[index + 1]
            queue = [item for item in queue if item != resource_key]
            queue.append(resource_key)
            data[resource_key] = resource_json
            index += 2

        remove_count = int(arguments[index])
        index += 1
        for _ in range(remove_count):
            resource_key = arguments[index]
            queue = [item for item in queue if item != resource_key]
            data.pop(resource_key, None)
            index += 1

        while len(queue) > capacity:
            data.pop(queue.pop(0), None)

        self.lists[queue_key] = queue
        self.hashes[data_key] = data
        self.strings[version_key] = version
        return len(queue)

    def _replace(self, keys, arguments) -> None:
        queue_key, data_key, version_key = keys
        item_count = int(arguments[0])
        index = 1
        queue = []
        data = {}
        for _ in range(item_count):
            resource_key = arguments[index]
            resource_json = arguments[index + 1]
            queue.append(resource_key)
            data[resource_key] = resource_json
            index += 2
        self.lists[queue_key] = queue
        self.hashes[data_key] = data
        self.strings[version_key] = str(arguments[index])
        return item_count


def _resource(
    resource_id: str,
    *,
    seen_at: datetime,
) -> ContextResourceRef:
    return ContextResourceRef(
        resource_key=f"document:{resource_id}",
        resource_type="document",
        resource_id=resource_id,
        summary=f"文档 {resource_id}",
        source_turn_id=f"turn-{resource_id}",
        last_seen_at=seen_at,
    )


class ContextResourceQueueRepositoryTest(
    unittest.IsolatedAsyncioTestCase
):
    async def test_refreshes_existing_item_to_tail_and_trims_head(
        self,
    ) -> None:
        client = _RedisClient()
        repository = ContextResourceQueueRepository(client, capacity=4)
        now = datetime.now()
        initial = [
            _resource(item, seen_at=now + timedelta(seconds=index))
            for index, item in enumerate(["A", "B", "C", "D"])
        ]

        await repository.replace(
            conversation_id="conversation-1",
            chain_id="chain-1",
            resources=initial,
            database_version=1,
        )
        await repository.refresh(
            conversation_id="conversation-1",
            chain_id="chain-1",
            resources=[
                _resource("B", seen_at=now + timedelta(seconds=5))
            ],
            removed_resource_keys=[],
            expected_previous_version=1,
            database_version=2,
        )
        await repository.refresh(
            conversation_id="conversation-1",
            chain_id="chain-1",
            resources=[
                _resource("E", seen_at=now + timedelta(seconds=6))
            ],
            removed_resource_keys=[],
            expected_previous_version=2,
            database_version=3,
        )

        queue = await repository.get(
            conversation_id="conversation-1",
            chain_id="chain-1",
            expected_version=3,
        )

        self.assertIsNotNone(queue)
        self.assertEqual(
            [item.resource_id for item in queue.items],
            ["C", "D", "B", "E"],
        )
        _, keys, _ = client.eval_calls[-1]
        self.assertEqual(
            keys,
            [
                "ctx:{conversation-1}:chain:chain-1:resource:queue",
                "ctx:{conversation-1}:chain:chain-1:resource:data",
                "ctx:{conversation-1}:chain:chain-1:resource:version",
            ],
        )

    async def test_removes_resource_and_version_mismatch_misses(
        self,
    ) -> None:
        client = _RedisClient()
        repository = ContextResourceQueueRepository(client, capacity=2)
        now = datetime.now()
        await repository.replace(
            conversation_id="conversation-1",
            chain_id="chain-1",
            resources=[
                _resource("A", seen_at=now),
                _resource("B", seen_at=now),
            ],
            database_version=1,
        )
        await repository.refresh(
            conversation_id="conversation-1",
            chain_id="chain-1",
            resources=[],
            removed_resource_keys=["document:A"],
            expected_previous_version=1,
            database_version=2,
        )

        self.assertIsNone(
            await repository.get(
                conversation_id="conversation-1",
                chain_id="chain-1",
                expected_version=1,
            )
        )
        queue = await repository.get(
            conversation_id="conversation-1",
            chain_id="chain-1",
            expected_version=2,
        )
        self.assertEqual(
            [item.resource_id for item in queue.items],
            ["B"],
        )

    async def test_rejects_incremental_refresh_when_previous_cache_missing(
        self,
    ) -> None:
        client = _RedisClient()
        repository = ContextResourceQueueRepository(client, capacity=4)

        applied = await repository.refresh(
            conversation_id="conversation-1",
            chain_id="chain-1",
            resources=[
                _resource("B", seen_at=datetime.now())
            ],
            removed_resource_keys=[],
            expected_previous_version=1,
            database_version=2,
        )

        self.assertFalse(applied)
        self.assertIsNone(
            await repository.get(
                conversation_id="conversation-1",
                chain_id="chain-1",
                expected_version=2,
            )
        )


class RedisClientFactoryTest(unittest.IsolatedAsyncioTestCase):
    async def test_creates_decoded_async_client_without_connecting(
        self,
    ) -> None:
        client = create_redis_client(
            "redis://127.0.0.1:6379/3",
            socket_connect_timeout_seconds=4,
            socket_timeout_seconds=6,
        )
        try:
            settings = client.connection_pool.connection_kwargs
            self.assertEqual(settings["host"], "127.0.0.1")
            self.assertEqual(settings["port"], 6379)
            self.assertEqual(settings["db"], 3)
            self.assertTrue(settings["decode_responses"])
            self.assertEqual(settings["socket_connect_timeout"], 4)
            self.assertEqual(settings["socket_timeout"], 6)
        finally:
            await close_redis_client(client)


class ContextResourceMigrationTest(unittest.TestCase):
    def test_converts_legacy_resource_snapshot_without_duplicates(
        self,
    ) -> None:
        migration = _load_migration_module()
        pairs = migration._legacy_resource_pairs(
            {
                "document_ids": [13, 13],
                "task_ids": ["task-1"],
                "other": {
                    "diagnosis_result": ["diag-1"],
                    "Invalid Type": ["legacy-1"],
                },
            }
        )

        self.assertEqual(
            pairs,
            [
                ("document", "13"),
                ("task", "task-1"),
                ("diagnosis_result", "diag-1"),
                ("other", "Invalid Type:legacy-1"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
