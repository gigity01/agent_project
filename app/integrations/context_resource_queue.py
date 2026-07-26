"""Context Chain Redis 刷新式 FIFO 热资源队列。"""

from __future__ import annotations

from redis.asyncio import Redis

from app.schemas.context import ContextResourceQueue, ContextResourceRef


REFRESH_QUEUE_LUA = """
local max_size = tonumber(ARGV[1])
local database_version = ARGV[2]
local expected_previous_version = ARGV[3]
local current_version = redis.call("GET", KEYS[3])
if current_version then
    if current_version ~= expected_previous_version then
        return -1
    end
elseif expected_previous_version ~= "0" then
    return -1
end

local refresh_count = tonumber(ARGV[4])
local index = 5

for _ = 1, refresh_count do
    local resource_key = ARGV[index]
    local resource_json = ARGV[index + 1]
    redis.call("LREM", KEYS[1], 0, resource_key)
    redis.call("RPUSH", KEYS[1], resource_key)
    redis.call("HSET", KEYS[2], resource_key, resource_json)
    index = index + 2
end

local remove_count = tonumber(ARGV[index])
index = index + 1
for _ = 1, remove_count do
    local resource_key = ARGV[index]
    redis.call("LREM", KEYS[1], 0, resource_key)
    redis.call("HDEL", KEYS[2], resource_key)
    index = index + 1
end

local length = redis.call("LLEN", KEYS[1])
while length > max_size do
    local removed = redis.call("LPOP", KEYS[1])
    if removed then
        redis.call("HDEL", KEYS[2], removed)
    end
    length = length - 1
end

redis.call("SET", KEYS[3], database_version)
return length
""".strip()


REPLACE_QUEUE_LUA = """
redis.call("DEL", KEYS[1])
redis.call("DEL", KEYS[2])

local item_count = tonumber(ARGV[1])
local index = 2
for _ = 1, item_count do
    local resource_key = ARGV[index]
    local resource_json = ARGV[index + 1]
    redis.call("RPUSH", KEYS[1], resource_key)
    redis.call("HSET", KEYS[2], resource_key, resource_json)
    index = index + 2
end

redis.call("SET", KEYS[3], ARGV[index])
return item_count
""".strip()


def _as_text(value: str | bytes | int) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


class ContextResourceQueueRepository:
    """使用 Redis List、Hash 和版本 Key 保存有界热资源队列。"""

    def __init__(self, client: Redis, *, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("Context resource queue capacity must be positive")
        self._client = client
        self.capacity = capacity

    @staticmethod
    def _keys(conversation_id: str, chain_id: str) -> tuple[str, str, str]:
        prefix = f"ctx:{{{conversation_id}}}:chain:{chain_id}:resource"
        return (
            f"{prefix}:queue",
            f"{prefix}:data",
            f"{prefix}:version",
        )

    async def get(
        self,
        *,
        conversation_id: str,
        chain_id: str,
        expected_version: int,
    ) -> ContextResourceQueue | None:
        """版本一致且 List/Hash 完整时返回热队列，否则返回未命中。"""
        queue_key, data_key, version_key = self._keys(
            conversation_id,
            chain_id,
        )
        raw_version = await self._client.get(version_key)
        if (
            raw_version is None
            or _as_text(raw_version) != str(expected_version)
        ):
            return None

        raw_keys = await self._client.lrange(queue_key, 0, -1)
        resource_keys = [_as_text(item) for item in raw_keys]
        if not resource_keys:
            return ContextResourceQueue(capacity=self.capacity)
        if len(resource_keys) > self.capacity:
            return None

        raw_items = await self._client.hmget(data_key, resource_keys)
        if len(raw_items) != len(resource_keys):
            return None

        items: list[ContextResourceRef] = []
        for resource_key, raw_item in zip(
            resource_keys,
            raw_items,
            strict=True,
        ):
            if raw_item is None:
                return None
            item = ContextResourceRef.model_validate_json(
                _as_text(raw_item)
            )
            if item.resource_key != resource_key:
                return None
            items.append(item)

        return ContextResourceQueue(
            capacity=self.capacity,
            items=items,
        )

    async def refresh(
        self,
        *,
        conversation_id: str,
        chain_id: str,
        resources: list[ContextResourceRef],
        removed_resource_keys: list[str],
        expected_previous_version: int,
        database_version: int,
    ) -> bool:
        """版本连续时原子刷新资源；缓存缺口返回 False。"""
        keys = self._keys(conversation_id, chain_id)
        arguments: list[str | int] = [
            self.capacity,
            database_version,
            expected_previous_version,
            len(resources),
        ]
        for resource in resources:
            arguments.extend(
                [resource.resource_key, resource.model_dump_json()]
            )
        arguments.append(len(removed_resource_keys))
        arguments.extend(removed_resource_keys)
        result = await self._client.eval(
            REFRESH_QUEUE_LUA,
            len(keys),
            *keys,
            *arguments,
        )
        return int(result) >= 0

    async def replace(
        self,
        *,
        conversation_id: str,
        chain_id: str,
        resources: list[ContextResourceRef],
        database_version: int,
    ) -> None:
        """使用数据库最近资源原子替换整个 Redis 队列。"""
        resources = resources[-self.capacity :]
        keys = self._keys(conversation_id, chain_id)
        arguments: list[str | int] = [len(resources)]
        for resource in resources:
            arguments.extend(
                [resource.resource_key, resource.model_dump_json()]
            )
        arguments.append(database_version)
        await self._client.eval(
            REPLACE_QUEUE_LUA,
            len(keys),
            *keys,
            *arguments,
        )

    async def invalidate(
        self,
        *,
        conversation_id: str,
        chain_id: str,
    ) -> None:
        """删除热队列；数据库资源事实不受影响。"""
        await self._client.delete(
            *self._keys(conversation_id, chain_id)
        )
